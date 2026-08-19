"""Allowlisted Home Assistant adapter for Autumn Phase 3E.

Model-visible Home stays intentionally small: list / state / control only.
Companion-only discovery and authorization are separate methods and never expose
Home Assistant entity IDs, domains, service names, or the HA token to the model.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, ProxyHandler

HOME_CONFIG_PATH = Path(os.environ.get(
    "AUTUMN_HOME_CONFIG",
    str(Path.home() / ".config" / "autumn" / "home.json"),
))
HOME_TOKEN_PATH = Path(os.environ.get(
    "AUTUMN_HOME_ASSISTANT_TOKEN_PATH",
    str(Path.home() / ".config" / "autumn" / "home-assistant.token"),
))
HOME_ASSISTANT_URL = "http://127.0.0.1:8123"
MAX_CONFIG_BYTES = 64 * 1024
MAX_DEVICES = 32
MAX_ATTRIBUTES = 16
MAX_ACTIONS = 12
MAX_DISCOVERY_CANDIDATES = 64
META_CACHE_SECONDS = 300
ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")
ENTITY_ID_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")
NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
CANDIDATE_RE = re.compile(r"^[a-f0-9]{24}$")

DENIED_DOMAINS = frozenset(("lock", "alarm_control_panel", "camera"))
DISCOVERY_DOMAINS = frozenset(("light", "switch", "fan", "media_player", "sensor"))
COMMAND_SERVICE = {
    "light": {"on": "turn_on", "off": "turn_off"},
    "switch": {"on": "turn_on", "off": "turn_off"},
    "fan": {"on": "turn_on", "off": "turn_off", "set_speed": "set_percentage"},
    "media_player": {"play": "media_play", "pause": "media_pause", "set_volume": "volume_set"},
}


class HomeError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # pragma: no cover - urllib hook
        return None


class HomeAdapter:
    """Read/control only devices explicitly present in the local allowlist."""

    def __init__(self, config_path: Path = HOME_CONFIG_PATH, token_path: Path = HOME_TOKEN_PATH, opener=None, clock=time.monotonic):
        self.config_path = Path(config_path)
        self.token_path = Path(token_path)
        self._open = opener or build_opener(ProxyHandler({}), _NoRedirect()).open
        self._clock = clock
        self._meta_cache: dict[str, tuple[float, dict[str, str]]] = {}

    def configured(self) -> bool:
        try:
            self._load_config()
            self._read_token()
            return True
        except HomeError:
            return False

    # ------------------------- model-visible contract -------------------------

    def handle(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise HomeError("HOME_REQUEST_INVALID", "home request must be an object")
        action = payload.get("action")
        if action == "list" and set(payload) == {"action"}:
            return self.list_devices()
        if action == "state" and set(payload) == {"action", "device"}:
            return self.read_state(payload.get("device"))
        if action == "control" and set(payload) in (
            {"action", "device", "command"},
            {"action", "device", "command", "value"},
        ):
            return self.control(
                payload.get("device"), payload.get("command"), payload.get("value"), "value" in payload,
            )
        raise HomeError("HOME_REQUEST_INVALID", "unsupported home request")

    def list_devices(self) -> dict[str, object]:
        config = self._load_config()
        devices = []
        for alias, spec in config["devices"].items():
            devices.append({
                "device": alias,
                "label": spec["label"],
                "readable": bool(spec["read"]),
                "commands": sorted(spec["actions"]),
                "risk": spec["risk"],
                "confirm": spec["confirm"],
            })
        return {"status": "OK", "devices": devices}

    def read_state(self, alias: object) -> dict[str, object]:
        alias, spec = self._device(alias)
        if not spec["read"]:
            raise HomeError("HOME_DEVICE_NOT_FOUND", "device not found", 404)
        state = self._request_json("GET", f"/api/states/{spec['entity_id']}")
        return {
            "status": "OK",
            "device": alias,
            "label": spec["label"],
            "state": self._sanitize_state(state, spec["read"]),
        }
    def control(self, alias: object, command: object, value: object = None, value_present: bool = False) -> dict[str, object]:
        alias, spec = self._device(alias)
        if not isinstance(command, str) or not NAME_RE.fullmatch(command):
            raise HomeError("HOME_COMMAND_NOT_ALLOWED", "command is not allowed", 404)
        action = spec["actions"].get(command)
        if action is None:
            raise HomeError("HOME_COMMAND_NOT_ALLOWED", "command is not allowed", 404)

        domain = spec["entity_id"].split(".", 1)[0]
        body: dict[str, object] = {"entity_id": spec["entity_id"], **action["data"]}
        if command == "set_speed":
            if domain != "fan" or not value_present or isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise HomeError("HOME_VALUE_NOT_ALLOWED", "fan speed must be an integer from 0 to 100")
            body["percentage"] = value
        elif command == "set_volume":
            if domain != "media_player" or not value_present or isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise HomeError("HOME_VALUE_NOT_ALLOWED", "speaker volume must be an integer from 0 to 100")
            body["volume_level"] = value / 100
        elif value_present:
            raise HomeError("HOME_VALUE_NOT_ALLOWED", "this command does not accept a value")

        self._request_json("POST", f"/api/services/{domain}/{action['service']}", body)
        state = self._request_json("GET", f"/api/states/{spec['entity_id']}")
        return {
            "status": "OK",
            "device": alias,
            "label": spec["label"],
            "command": command,
            "state": self._sanitize_state(state, spec["read"]),
        }

    # --------------------- Companion-only presentation API -------------------

    def companion_devices(self) -> dict[str, object]:
        """Return allowlisted devices as human-facing logical cards.

        Temperature and humidity entities belonging to the same HA device are
        intentionally merged into one logical card. Underlying entity IDs stay
        private and model-visible aliases remain unchanged.
        """
        config = self._load_config()
        states = self._state_map()
        rows: list[dict[str, object]] = []
        for alias, spec in config["devices"].items():
            entity_id = spec["entity_id"]
            state = states.get(entity_id)
            attrs = state.get("attributes") if isinstance(state, dict) and isinstance(state.get("attributes"), dict) else {}
            meta = self._entity_meta(entity_id)
            domain = entity_id.split(".", 1)[0]
            device_class = str(attrs.get("device_class") or "")[:40]
            rows.append({
                "alias": alias,
                "label": spec["label"],
                "domain": domain,
                "device_class": device_class,
                "device_id": meta["device_id"],
                "device_name": meta["device_name"],
                "room": meta["area_name"] or "未分区",
                "commands": sorted(spec["actions"]),
                "state": self._sanitize_state(state, spec["read"]) if state else {},
            })

        used: set[str] = set()
        logical: list[dict[str, object]] = []
        by_device: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            device_id = str(row["device_id"] or "")
            if device_id:
                by_device.setdefault(device_id, []).append(row)

        for device_id, members in by_device.items():
            temps = [x for x in members if x["domain"] == "sensor" and x["device_class"] == "temperature"]
            hums = [x for x in members if x["domain"] == "sensor" and x["device_class"] == "humidity"]
            if not temps or not hums:
                continue
            temp, hum = temps[0], hums[0]
            used.update((str(temp["alias"]), str(hum["alias"])))
            label = str(temp["device_name"] or hum["device_name"] or self._common_sensor_label(str(temp["label"]), str(hum["label"])))[:80]
            logical.append({
                "device": self._public_logical_id("climate", [str(temp["alias"]), str(hum["alias"])]),
                "label": label or "温湿度计",
                "room": str(temp["room"] or hum["room"] or "未分区")[:80],
                "kind": "climate_sensor",
                "controllable": False,
                "commands": [],
                "state": {
                    "temperature": temp["state"].get("state"),
                    "temperature_unit": temp["state"].get("unit_of_measurement"),
                    "humidity": hum["state"].get("state"),
                    "humidity_unit": hum["state"].get("unit_of_measurement"),
                },
            })

        for row in rows:
            if row["alias"] in used:
                continue
            logical.append(self._logical_from_row(row))

        logical.sort(key=lambda item: (str(item.get("room") or ""), str(item.get("label") or "")))
        return {"status": "OK", "devices": logical}

    def discover_candidates(self) -> dict[str, object]:
        candidates, unsupported_count = self._discover_internal()
        public = [{
            "candidate_id": item["candidate_id"],
            "label": item["label"],
            "room": item["room"],
            "kind": item["kind"],
            "capabilities": list(item["capabilities"]),
        } for item in candidates[:MAX_DISCOVERY_CANDIDATES]]
        return {"status": "OK", "candidates": public, "unsupported_count": unsupported_count}

    def authorize_candidate(self, candidate_id: object) -> dict[str, object]:
        if not isinstance(candidate_id, str) or not CANDIDATE_RE.fullmatch(candidate_id):
            raise HomeError("HOME_CANDIDATE_NOT_FOUND", "candidate not found", 404)
        candidates, _ = self._discover_internal()
        candidate = next((item for item in candidates if item["candidate_id"] == candidate_id), None)
        if candidate is None:
            raise HomeError("HOME_CANDIDATE_NOT_FOUND", "candidate not found", 404)

        config = self._load_config()
        devices = dict(config["devices"])
        members = candidate["members"]
        if len(devices) + len(members) > MAX_DEVICES:
            raise HomeError("HOME_CONFIG_FULL", "home allowlist is full", 409)
        used = set(devices)
        for member in members:
            alias = self._new_alias(str(member["kind"]), str(member["entity_id"]), used)
            used.add(alias)
            devices[alias] = self._spec_for_member(member, str(candidate["label"]))
        self._write_config({"version": 1, "devices": devices})
        return {
            "status": "OK",
            "candidate_id": candidate_id,
            "label": candidate["label"],
            "kind": candidate["kind"],
            "added": len(members),
        }

    # ---------------------------- discovery internals ------------------------

    def _discover_internal(self) -> tuple[list[dict[str, object]], int]:
        config = self._load_config()
        existing_entity_ids = {str(spec["entity_id"]) for spec in config["devices"].values()}
        existing_device_ids: set[str] = set()
        for entity_id in existing_entity_ids:
            meta = self._entity_meta(entity_id)
            device_id = str(meta.get("device_id") or "")
            if device_id:
                existing_device_ids.add(device_id)

        supported: list[dict[str, object]] = []
        unsupported_count = 0
        for state in self._all_states():
            if not isinstance(state, dict) or not isinstance(state.get("entity_id"), str):
                continue
            entity_id = str(state["entity_id"])
            if entity_id in existing_entity_ids or not ENTITY_ID_RE.fullmatch(entity_id):
                continue
            if state.get("state") in ("unknown", "unavailable"):
                continue
            domain = entity_id.split(".", 1)[0]
            attrs = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            device_class = str(attrs.get("device_class") or "")[:40]
            if domain == "sensor" and device_class not in ("temperature", "humidity"):
                unsupported_count += 1
                continue
            if domain not in DISCOVERY_DOMAINS:
                unsupported_count += 1
                continue
            meta = self._entity_meta(entity_id)
            supported.append({
                "entity_id": entity_id,
                "domain": domain,
                "device_class": device_class,
                "device_id": str(meta.get("device_id") or ""),
                "label": str(meta.get("device_name") or attrs.get("friendly_name") or entity_id.split(".", 1)[1])[:80],
                "room": str(meta.get("area_name") or "未分区")[:80],
            })

        groups: dict[str, list[dict[str, object]]] = {}
        for item in supported:
            device_id = str(item["device_id"] or "")
            key = "device:" + device_id if device_id else "entity:" + str(item["entity_id"])
            groups.setdefault(key, []).append(item)

        out: list[dict[str, object]] = []
        for key, members in groups.items():
            if key.startswith("device:") and key.removeprefix("device:") in existing_device_ids:
                continue
            candidate = self._candidate_from_physical_group(members)
            if candidate is not None:
                out.append(candidate)
        out.sort(key=lambda item: (str(item["room"]), str(item["label"])))
        return out[:MAX_DISCOVERY_CANDIDATES], unsupported_count

    def _candidate_from_physical_group(self, members: list[dict[str, object]]) -> dict[str, object] | None:
        if not members:
            return None

        def first(domain: str):
            return next((item for item in members if item["domain"] == domain), None)

        label = str(next((item["label"] for item in members if item.get("label")), "Home Device"))[:80]
        room = str(next((item["room"] for item in members if item.get("room")), "未分区"))[:80]
        fan = first("fan")
        if fan is not None:
            return self._candidate("fan", label, room, [{**fan, "kind": "fan"}], ["on", "off", "speed"])
        speaker = first("media_player")
        if speaker is not None:
            return self._candidate("speaker", label, room, [{**speaker, "kind": "speaker"}], ["play", "pause", "volume"])
        light = first("light")
        if light is not None:
            return self._candidate("light", label, room, [{**light, "kind": "light"}], ["on", "off"])
        temperature = next((item for item in members if item["domain"] == "sensor" and item["device_class"] == "temperature"), None)
        humidity = next((item for item in members if item["domain"] == "sensor" and item["device_class"] == "humidity"), None)
        if temperature is not None and humidity is not None:
            return self._candidate("climate_sensor", label, room, [{**temperature, "kind": "temperature"}, {**humidity, "kind": "humidity"}], ["temperature", "humidity"])
        switch = first("switch")
        if switch is not None:
            return self._candidate("switch", label, room, [{**switch, "kind": "switch"}], ["on", "off"])
        if temperature is not None:
            return self._candidate("temperature", label, room, [{**temperature, "kind": "temperature"}], ["temperature"])
        if humidity is not None:
            return self._candidate("humidity", label, room, [{**humidity, "kind": "humidity"}], ["humidity"])
        return None

    def _candidate(self, kind: str, label: str, room: str, members: list[dict[str, object]], capabilities: list[str]) -> dict[str, object]:
        entity_ids = sorted(str(item["entity_id"]) for item in members)
        return {
            "candidate_id": self._candidate_id(entity_ids),
            "label": label[:80],
            "room": room[:80] or "未分区",
            "kind": kind,
            "capabilities": capabilities,
            "members": members,
        }

    def _candidate_id(self, entity_ids: list[str]) -> str:
        token = self._read_token().encode("utf-8")
        message = ("autumn-home-candidate-v1\0" + "\0".join(entity_ids)).encode("utf-8")
        return hmac.new(token, message, hashlib.sha256).hexdigest()[:24]

    def _new_alias(self, kind: str, entity_id: str, used: set[str]) -> str:
        base_kind = {
            "speaker": "speaker", "fan": "fan", "light": "light", "switch": "switch",
            "temperature": "temperature", "humidity": "humidity",
        }.get(kind, "device")
        suffix = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()[:8]
        base = f"{base_kind}_{suffix}"
        alias = base
        counter = 2
        while alias in used:
            alias = f"{base}_{counter}"
            counter += 1
        return alias[:48]

    def _spec_for_member(self, member: dict[str, object], logical_label: str) -> dict[str, object]:
        entity_id = str(member["entity_id"])
        kind = str(member["kind"])
        if kind == "light":
            return self._spec(logical_label, entity_id, ["state", "brightness"], {"on": "turn_on", "off": "turn_off"})
        if kind == "switch":
            return self._spec(logical_label, entity_id, ["state"], {"on": "turn_on", "off": "turn_off"})
        if kind == "fan":
            return self._spec(logical_label, entity_id, ["state", "percentage"], {"on": "turn_on", "off": "turn_off", "set_speed": "set_percentage"})
        if kind == "speaker":
            return self._spec(logical_label, entity_id, ["state", "volume_level", "media_title"], {"play": "media_play", "pause": "media_pause", "set_volume": "volume_set"})
        if kind == "temperature":
            return self._spec(logical_label + " · 温度", entity_id, ["state", "unit_of_measurement"], {})
        if kind == "humidity":
            return self._spec(logical_label + " · 湿度", entity_id, ["state", "unit_of_measurement"], {})
        raise HomeError("HOME_CANDIDATE_NOT_FOUND", "candidate not supported", 404)

    @staticmethod
    def _spec(label: str, entity_id: str, read: list[str], actions: dict[str, str]) -> dict[str, object]:
        return {
            "label": label[:80],
            "entity_id": entity_id,
            "read": read,
            "risk": "low",
            "confirm": False,
            "actions": {command: {"service": service} for command, service in actions.items()},
        }

    # ----------------------------- config + HA I/O ---------------------------

    def _device(self, alias: object):
        if not isinstance(alias, str) or not ALIAS_RE.fullmatch(alias):
            raise HomeError("HOME_DEVICE_NOT_FOUND", "device not found", 404)
        spec = self._load_config()["devices"].get(alias)
        if spec is None:
            raise HomeError("HOME_DEVICE_NOT_FOUND", "device not found", 404)
        return alias, spec

    def _load_config(self) -> dict[str, object]:
        path = self.config_path
        if not path.is_file() or path.is_symlink():
            raise HomeError("HOME_NOT_CONFIGURED", "Autumn Home allowlist is not configured", 503)
        try:
            if path.stat().st_size > MAX_CONFIG_BYTES:
                raise HomeError("HOME_CONFIG_INVALID", "home allowlist is too large", 503)
            raw = json.loads(path.read_text("utf-8"))
        except HomeError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503) from exc
        return self._validate_config(raw)

    def _write_config(self, raw: dict[str, object]) -> None:
        clean = self._validate_config(raw)
        path = self.config_path
        if path.exists() and path.is_symlink():
            raise HomeError("HOME_CONFIG_INVALID", "home allowlist path must not be a symlink", 503)
        parent = path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=parent, prefix=path.name + ".", delete=False) as handle:
                temp_name = handle.name
                json.dump(clean, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
            os.chmod(path, 0o600)
        except OSError as exc:
            raise HomeError("HOME_CONFIG_WRITE_FAILED", "home allowlist update failed", 500) from exc
        finally:
            if temp_name:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    pass

    def _validate_config(self, raw: object) -> dict[str, object]:
        if not isinstance(raw, dict) or set(raw) != {"version", "devices"} or raw.get("version") != 1:
            raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
        devices = raw.get("devices")
        if not isinstance(devices, dict) or len(devices) > MAX_DEVICES:
            raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
        clean: dict[str, dict[str, object]] = {}
        for alias, spec in devices.items():
            if not isinstance(alias, str) or not ALIAS_RE.fullmatch(alias) or not isinstance(spec, dict):
                raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
            if set(spec) != {"label", "entity_id", "read", "actions", "risk", "confirm"}:
                raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
            label, entity_id, read, actions = spec["label"], spec["entity_id"], spec["read"], spec["actions"]
            risk, confirm = spec["risk"], spec["confirm"]
            if not isinstance(label, str) or not label.strip() or len(label) > 80:
                raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
            if not isinstance(entity_id, str) or not ENTITY_ID_RE.fullmatch(entity_id):
                raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
            domain = entity_id.split(".", 1)[0]
            if domain in DENIED_DOMAINS or risk != "low" or confirm is not False:
                raise HomeError("HOME_CONFIG_INVALID", "only low-risk non-confirmed V0.3 devices are supported", 503)
            if not isinstance(read, list) or len(read) > MAX_ATTRIBUTES or not all(isinstance(x, str) and NAME_RE.fullmatch(x) for x in read):
                raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
            if not isinstance(actions, dict) or len(actions) > MAX_ACTIONS:
                raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
            clean_actions: dict[str, dict[str, object]] = {}
            allowed_pairs = COMMAND_SERVICE.get(domain, {})
            for command, action in actions.items():
                if not isinstance(command, str) or not NAME_RE.fullmatch(command) or not isinstance(action, dict):
                    raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
                if set(action) - {"service", "data"} or set(action) < {"service"}:
                    raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
                service, data = action["service"], action.get("data", {})
                if not isinstance(service, str) or allowed_pairs.get(command) != service:
                    raise HomeError("HOME_CONFIG_INVALID", "home command/service mapping is not allowed", 503)
                if not isinstance(data, dict) or len(data) > 12:
                    raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
                for key, value in data.items():
                    if not isinstance(key, str) or not NAME_RE.fullmatch(key) or not isinstance(value, (str, int, float, bool, type(None))):
                        raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
                clean_actions[command] = {"service": service, "data": dict(data)}
            clean[alias] = {
                "label": label.strip(),
                "entity_id": entity_id,
                "read": list(dict.fromkeys(read)),
                "actions": clean_actions,
                "risk": "low",
                "confirm": False,
            }
        return {"version": 1, "devices": clean}

    def _read_token(self) -> str:
        path = self.token_path
        if not path.is_file() or path.is_symlink():
            raise HomeError("HOME_NOT_CONFIGURED", "Home Assistant token is not configured", 503)
        try:
            size = path.stat().st_size
            if not 20 <= size <= 4096:
                raise HomeError("HOME_TOKEN_INVALID", "Home Assistant token is invalid", 503)
            token = path.read_text("utf-8").strip()
        except HomeError:
            raise
        except (OSError, UnicodeError) as exc:
            raise HomeError("HOME_TOKEN_INVALID", "Home Assistant token is invalid", 503) from exc
        if len(token) < 20 or any(ch.isspace() for ch in token):
            raise HomeError("HOME_TOKEN_INVALID", "Home Assistant token is invalid", 503)
        return token

    def _all_states(self) -> list[dict[str, object]]:
        payload = self._request_json("GET", "/api/states")
        if not isinstance(payload, list):
            raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant returned invalid states", 502)
        return [item for item in payload if isinstance(item, dict)]

    def _state_map(self) -> dict[str, dict[str, object]]:
        return {
            str(item["entity_id"]): item
            for item in self._all_states()
            if isinstance(item.get("entity_id"), str) and ENTITY_ID_RE.fullmatch(str(item["entity_id"]))
        }

    def _entity_meta(self, entity_id: str) -> dict[str, str]:
        now = self._clock()
        cached = self._meta_cache.get(entity_id)
        if cached and cached[0] > now:
            return dict(cached[1])
        if not ENTITY_ID_RE.fullmatch(entity_id):
            return {"device_id": "", "device_name": "", "area_name": ""}
        template = (
            "{{ device_id('" + entity_id + "') or '' }}\n"
            "{{ device_name('" + entity_id + "') or '' }}\n"
            "{{ area_name('" + entity_id + "') or '' }}"
        )
        text = self._request_text("POST", "/api/template", {"template": template})
        lines = text.splitlines()
        while len(lines) < 3:
            lines.append("")
        meta = {
            "device_id": self._clean_meta(lines[0], 128),
            "device_name": self._clean_meta(lines[1], 80),
            "area_name": self._clean_meta(lines[2], 80),
        }
        self._meta_cache[entity_id] = (now + META_CACHE_SECONDS, meta)
        return dict(meta)

    @staticmethod
    def _clean_meta(value: str, limit: int) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]

    def _request_json(self, method: str, path: str, body: dict[str, object] | None = None):
        raw = self._request(method, path, body)
        try:
            payload = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant returned an invalid response", 502) from exc
        if not isinstance(payload, (dict, list)):
            raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant returned an invalid response", 502)
        return payload

    def _request_text(self, method: str, path: str, body: dict[str, object] | None = None) -> str:
        raw = self._request(method, path, body)
        try:
            return raw.decode("utf-8")
        except UnicodeError as exc:
            raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant returned invalid text", 502) from exc

    def _request(self, method: str, path: str, body: dict[str, object] | None = None) -> bytes:
        if not path.startswith("/api/"):
            raise HomeError("HOME_ADAPTER_INVALID", "invalid Home Assistant path", 500)
        token = self._read_token()
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = Request(
            HOME_ASSISTANT_URL + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/plain",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._open(request, timeout=4) as response:
                if response.status not in (200, 201):
                    raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant rejected the request", 502)
                return response.read()
        except HTTPError as exc:
            status = 404 if exc.code == 404 and method == "GET" else 502
            code = "HOME_DEVICE_UNAVAILABLE" if status == 404 else "HOME_ASSISTANT_FAILED"
            raise HomeError(code, "Home Assistant request failed", status) from exc
        except (OSError, URLError, TimeoutError) as exc:
            raise HomeError("HOME_ASSISTANT_UNAVAILABLE", "Home Assistant is unavailable", 502) from exc

    @staticmethod
    def _sanitize_state(payload: object, allowed: list[str]) -> dict[str, object]:
        if not isinstance(payload, dict) or not isinstance(payload.get("state"), str):
            raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant returned an invalid state", 502)
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        out: dict[str, object] = {}
        if "state" in allowed:
            out["state"] = payload["state"][:160]
        for name in allowed:
            if name == "state" or name not in attributes:
                continue
            value = attributes[name]
            if isinstance(value, (str, int, float, bool, type(None))):
                out[name] = value[:240] if isinstance(value, str) else value
        return out

    @staticmethod
    def _common_sensor_label(a: str, b: str) -> str:
        for suffix in (" · 温度", " 温度", "Temperature", "temperature", " · 湿度", " 湿度", "Humidity", "humidity"):
            a = a.replace(suffix, "").strip()
            b = b.replace(suffix, "").strip()
        return a if a and a == b else (a or b or "温湿度计")

    @staticmethod
    def _public_logical_id(prefix: str, aliases: list[str]) -> str:
        digest = hashlib.sha256("\0".join(sorted(aliases)).encode("utf-8")).hexdigest()[:8]
        return f"{prefix}_{digest}"

    @staticmethod
    def _logical_from_row(row: dict[str, object]) -> dict[str, object]:
        domain = str(row["domain"])
        device_class = str(row["device_class"])
        kind = (
            "speaker" if domain == "media_player" else
            "fan" if domain == "fan" else
            "light" if domain == "light" else
            "switch" if domain == "switch" else
            device_class if device_class in ("temperature", "humidity") else "sensor"
        )
        return {
            "device": row["alias"],
            "label": row["device_name"] or row["label"],
            "room": row["room"],
            "kind": kind,
            "controllable": bool(row["commands"]),
            "commands": list(row["commands"]),
            "state": dict(row["state"]),
        }
