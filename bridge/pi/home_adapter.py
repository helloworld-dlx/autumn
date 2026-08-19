"""Minimal allowlisted Home Assistant adapter for Autumn Phase 3E.

The model never receives Home Assistant entity IDs and never supplies Home
Assistant domains/services.  Those values stay in a device-local allowlist.
"""
from __future__ import annotations

import json
import os
import re
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
ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")
ENTITY_ID_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$")
NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
CONTROL_DOMAINS = frozenset(("light", "switch"))
CONTROL_SERVICES = frozenset(("turn_on", "turn_off", "toggle"))
DENIED_DOMAINS = frozenset(("lock", "alarm_control_panel", "camera"))


class HomeError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # pragma: no cover - urllib hook
        return None


class HomeAdapter:
    """Read/control only devices explicitly present in the local allowlist."""

    def __init__(self, config_path: Path = HOME_CONFIG_PATH, token_path: Path = HOME_TOKEN_PATH, opener=None):
        self.config_path = Path(config_path)
        self.token_path = Path(token_path)
        self._open = opener or build_opener(ProxyHandler({}), _NoRedirect()).open

    def configured(self) -> bool:
        try:
            self._load_config()
            self._read_token()
            return True
        except HomeError:
            return False

    def handle(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise HomeError("HOME_REQUEST_INVALID", "home request must be an object")
        action = payload.get("action")
        if action == "list" and set(payload) == {"action"}:
            return self.list_devices()
        if action == "state" and set(payload) == {"action", "device"}:
            return self.read_state(payload.get("device"))
        if action == "control" and set(payload) == {"action", "device", "command"}:
            return self.control(payload.get("device"), payload.get("command"))
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

    def control(self, alias: object, command: object) -> dict[str, object]:
        alias, spec = self._device(alias)
        if not isinstance(command, str) or not NAME_RE.fullmatch(command):
            raise HomeError("HOME_COMMAND_NOT_ALLOWED", "command is not allowed", 404)
        action = spec["actions"].get(command)
        if action is None:
            # Deliberately indistinguishable from an unknown command outside the allowlist.
            raise HomeError("HOME_COMMAND_NOT_ALLOWED", "command is not allowed", 404)
        domain = spec["entity_id"].split(".", 1)[0]
        body = {"entity_id": spec["entity_id"], **action["data"]}
        self._request_json("POST", f"/api/services/{domain}/{action['service']}", body)
        state = self._request_json("GET", f"/api/states/{spec['entity_id']}")
        return {
            "status": "OK",
            "device": alias,
            "label": spec["label"],
            "command": command,
            "state": self._sanitize_state(state, spec["read"]),
        }

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
            for command, action in actions.items():
                if not isinstance(command, str) or not NAME_RE.fullmatch(command) or not isinstance(action, dict):
                    raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
                if set(action) - {"service", "data"} or set(action) < {"service"}:
                    raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
                service, data = action["service"], action.get("data", {})
                if not isinstance(service, str) or not NAME_RE.fullmatch(service):
                    raise HomeError("HOME_CONFIG_INVALID", "home allowlist is invalid", 503)
                if domain not in CONTROL_DOMAINS or service not in CONTROL_SERVICES:
                    raise HomeError("HOME_CONFIG_INVALID", "home control is limited to low-risk light/switch commands", 503)
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

    def _request_json(self, method: str, path: str, body: dict[str, object] | None = None):
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
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._open(request, timeout=4) as response:
                if response.status not in (200, 201):
                    raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant rejected the request", 502)
                payload = json.loads(response.read())
        except HTTPError as exc:
            status = 404 if exc.code == 404 and method == "GET" else 502
            code = "HOME_DEVICE_UNAVAILABLE" if status == 404 else "HOME_ASSISTANT_FAILED"
            raise HomeError(code, "Home Assistant request failed", status) from exc
        except (OSError, URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            raise HomeError("HOME_ASSISTANT_UNAVAILABLE", "Home Assistant is unavailable", 502) from exc
        if not isinstance(payload, (dict, list)):
            raise HomeError("HOME_ASSISTANT_FAILED", "Home Assistant returned an invalid response", 502)
        return payload

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
