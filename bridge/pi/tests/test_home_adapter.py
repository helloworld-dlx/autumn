import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from io import BytesIO

from jarvis_bridge.home_adapter import HomeAdapter, HomeError


class Response:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload
    def read(self):
        return json.dumps(self._payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


class FakeOpen:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    def __call__(self, request, timeout=0):
        self.calls.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class HomeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = root / "home.json"
        self.token = root / "ha.token"
        self.token.write_text("t" * 64, encoding="utf-8")
        self.config.write_text(json.dumps({
            "version": 1,
            "devices": {
                "desk_lamp": {
                    "label": "Desk Lamp",
                    "entity_id": "light.private_lamp_id",
                    "read": ["state", "brightness"],
                    "risk": "low",
                    "confirm": False,
                    "actions": {
                        "on": {"service": "turn_on"},
                        "off": {"service": "turn_off"},
                    },
                },
                "room_temperature": {
                    "label": "Room Temperature",
                    "entity_id": "sensor.private_temperature_id",
                    "read": ["state", "unit_of_measurement"],
                    "risk": "low",
                    "confirm": False,
                    "actions": {},
                },
            },
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_list_is_allowlist_only_and_hides_entity_ids(self):
        adapter = HomeAdapter(self.config, self.token, opener=FakeOpen([]))
        result = adapter.handle({"action": "list"})
        self.assertEqual(result["status"], "OK")
        self.assertEqual([x["device"] for x in result["devices"]], ["desk_lamp", "room_temperature"])
        self.assertNotIn("entity_id", json.dumps(result))
        self.assertEqual(result["devices"][0]["commands"], ["off", "on"])

    def test_state_reads_only_configured_attributes(self):
        fake = FakeOpen([Response(200, {
            "entity_id": "light.private_lamp_id",
            "state": "on",
            "attributes": {"brightness": 172, "friendly_name": "SECRET NAME", "token": "nope"},
            "context": {"id": "private"},
        })])
        adapter = HomeAdapter(self.config, self.token, opener=fake)
        result = adapter.handle({"action": "state", "device": "desk_lamp"})
        self.assertEqual(result["state"], {"state": "on", "brightness": 172})
        self.assertNotIn("entity_id", json.dumps(result))
        self.assertNotIn("friendly_name", json.dumps(result))
        self.assertNotIn("private", json.dumps(result))
        request, timeout = fake.calls[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8123/api/states/light.private_lamp_id")
        self.assertEqual(request.method, "GET")
        self.assertEqual(timeout, 4)
        self.assertEqual(request.headers["Authorization"], "Bearer " + "t" * 64)

    def test_control_maps_alias_command_to_fixed_service_then_reads_back(self):
        fake = FakeOpen([
            Response(200, [{"entity_id": "light.private_lamp_id", "state": "on"}]),
            Response(200, {"state": "on", "attributes": {"brightness": 200}}),
        ])
        adapter = HomeAdapter(self.config, self.token, opener=fake)
        result = adapter.handle({"action": "control", "device": "desk_lamp", "command": "on"})
        self.assertEqual(result["command"], "on")
        self.assertEqual(result["state"], {"state": "on", "brightness": 200})
        first, _ = fake.calls[0]
        self.assertEqual(first.full_url, "http://127.0.0.1:8123/api/services/light/turn_on")
        self.assertEqual(first.method, "POST")
        self.assertEqual(json.loads(first.data), {"entity_id": "light.private_lamp_id"})
        second, _ = fake.calls[1]
        self.assertEqual(second.method, "GET")

    def test_unallowlisted_device_and_command_never_call_home_assistant(self):
        fake = FakeOpen([])
        adapter = HomeAdapter(self.config, self.token, opener=fake)
        with self.assertRaises(HomeError) as unknown:
            adapter.handle({"action": "state", "device": "door_lock"})
        self.assertEqual(unknown.exception.code, "HOME_DEVICE_NOT_FOUND")
        with self.assertRaises(HomeError) as command:
            adapter.handle({"action": "control", "device": "desk_lamp", "command": "unlock"})
        self.assertEqual(command.exception.code, "HOME_COMMAND_NOT_ALLOWED")
        self.assertEqual(fake.calls, [])

    def test_read_only_sensor_cannot_be_controlled(self):
        adapter = HomeAdapter(self.config, self.token, opener=FakeOpen([]))
        with self.assertRaises(HomeError) as caught:
            adapter.handle({"action": "control", "device": "room_temperature", "command": "on"})
        self.assertEqual(caught.exception.code, "HOME_COMMAND_NOT_ALLOWED")

    def test_request_shape_and_config_are_strict(self):
        adapter = HomeAdapter(self.config, self.token, opener=FakeOpen([]))
        with self.assertRaises(HomeError) as caught:
            adapter.handle({"action": "control", "device": "desk_lamp", "command": "on", "service": "unlock"})
        self.assertEqual(caught.exception.code, "HOME_REQUEST_INVALID")
        bad = json.loads(self.config.read_text("utf-8"))
        bad["devices"]["desk_lamp"]["secret"] = "nope"
        self.config.write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaises(HomeError) as config:
            adapter.handle({"action": "list"})
        self.assertEqual(config.exception.code, "HOME_CONFIG_INVALID")

    def test_symlink_token_is_rejected(self):
        root = Path(self.temp.name)
        real = root / "real-token"
        real.write_text("t" * 64, encoding="utf-8")
        link = root / "linked-token"
        try:
            link.symlink_to(real)
        except OSError as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")
        adapter = HomeAdapter(self.config, link, opener=FakeOpen([]))
        with self.assertRaises(HomeError) as caught:
            adapter.handle({"action": "state", "device": "desk_lamp"})
        self.assertEqual(caught.exception.code, "HOME_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
