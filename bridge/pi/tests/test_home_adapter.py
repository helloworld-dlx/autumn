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


class HomeFinalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.config = root / "home.json"; self.token = root / "ha.token"; self.token.write_text("t" * 64, encoding="utf-8")
        self.config.write_text(json.dumps({"version": 1, "devices": {
            "old_temp": {"label": "客厅温度", "entity_id": "sensor.old_temp", "read": ["state", "unit_of_measurement"], "actions": {}, "risk": "low", "confirm": False},
            "old_hum": {"label": "客厅湿度", "entity_id": "sensor.old_hum", "read": ["state", "unit_of_measurement"], "actions": {}, "risk": "low", "confirm": False},
        }}), encoding="utf-8")
        self.states = [
            {"entity_id":"sensor.old_temp","state":"26.4","attributes":{"device_class":"temperature","unit_of_measurement":"°C","friendly_name":"客厅温度"}},
            {"entity_id":"sensor.old_hum","state":"58","attributes":{"device_class":"humidity","unit_of_measurement":"%","friendly_name":"客厅湿度"}},
            {"entity_id":"fan.bedroom","state":"off","attributes":{"percentage":0,"friendly_name":"卧室风扇"}},
            {"entity_id":"switch.bedroom_fan_power","state":"off","attributes":{"friendly_name":"卧室风扇电源"}},
            {"entity_id":"media_player.speaker","state":"idle","attributes":{"volume_level":0.3,"friendly_name":"客厅音箱"}},
            {"entity_id":"switch.speaker_power","state":"off","attributes":{"friendly_name":"客厅音箱电源"}},
            {"entity_id":"sensor.new_temp","state":"25.2","attributes":{"device_class":"temperature","unit_of_measurement":"°C","friendly_name":"卧室温度"}},
            {"entity_id":"sensor.new_hum","state":"60","attributes":{"device_class":"humidity","unit_of_measurement":"%","friendly_name":"卧室湿度"}},
            {"entity_id":"camera.secret","state":"idle","attributes":{"friendly_name":"Secret Camera"}},
        ]
        self.meta={"sensor.old_temp":{"device_id":"dev_old","device_name":"客厅温湿度计","area_name":"客厅"},"sensor.old_hum":{"device_id":"dev_old","device_name":"客厅温湿度计","area_name":"客厅"},"fan.bedroom":{"device_id":"dev_fan","device_name":"卧室风扇","area_name":"卧室"},"switch.bedroom_fan_power":{"device_id":"dev_fan","device_name":"卧室风扇","area_name":"卧室"},"media_player.speaker":{"device_id":"dev_speaker","device_name":"客厅音箱","area_name":"客厅"},"switch.speaker_power":{"device_id":"dev_speaker","device_name":"客厅音箱","area_name":"客厅"},"sensor.new_temp":{"device_id":"dev_new","device_name":"卧室温湿度计","area_name":"卧室"},"sensor.new_hum":{"device_id":"dev_new","device_name":"卧室温湿度计","area_name":"卧室"}}
        self.router = self.Router(self.states, self.meta); self.adapter = HomeAdapter(self.config, self.token, opener=self.router)
    def tearDown(self): self.temp.cleanup()
    class Router:
        def __init__(self, states, meta): self.states=states; self.meta=meta; self.calls=[]; self.services=[]
        def __call__(self, request, timeout=0):
            self.calls.append((request, timeout)); url=request.full_url
            if url.endswith('/api/states'): return Response(200, self.states)
            if '/api/states/' in url: return Response(200, next(x for x in self.states if x['entity_id']==url.rsplit('/api/states/',1)[1]))
            if url.endswith('/api/template'):
                text=json.loads(request.data)['template']; eid=text.split("device_id('",1)[1].split("')",1)[0]; m=self.meta.get(eid,{})
                return Response(200, f"{m.get('device_id','')}\n{m.get('device_name','')}\n{m.get('area_name','')}")
            if '/api/services/' in url:
                body=json.loads(request.data); self.services.append((url,body)); item=next(x for x in self.states if x['entity_id']==body['entity_id']); service=url.rsplit('/',1)[1]
                if service=='set_percentage': item['attributes']['percentage']=body['percentage']; item['state']='on'
                if service=='volume_set': item['attributes']['volume_level']=body['volume_level']
                if service=='turn_on': item['state']='on'
                if service=='turn_off': item['state']='off'
                if service=='media_play': item['state']='playing'
                if service=='media_pause': item['state']='paused'
                return Response(200,[item])
            raise AssertionError(url)
    def test_companion_merge_and_discovery_are_sanitized(self):
        out=self.adapter.companion_devices(); self.assertEqual(len(out['devices']),1); self.assertEqual(out['devices'][0]['kind'],'climate_sensor'); self.assertNotIn('entity_id',json.dumps(out))
        disc=self.adapter.discover_candidates(); kinds=sorted(x['kind'] for x in disc['candidates']); self.assertEqual(kinds,['climate_sensor','fan','speaker']); self.assertNotIn('entity_id',json.dumps(disc)); self.assertNotIn('camera',json.dumps(disc).lower())
    def test_authorize_fan_and_speed(self):
        fan=next(x for x in self.adapter.discover_candidates()['candidates'] if x['kind']=='fan'); self.adapter.authorize_candidate(fan['candidate_id']); f=next(x for x in self.adapter.list_devices()['devices'] if 'set_speed' in x['commands']); out=self.adapter.handle({'action':'control','device':f['device'],'command':'set_speed','value':35}); self.assertEqual(out['state']['percentage'],35); self.assertTrue(self.router.services[-1][0].endswith('/fan/set_percentage'))
    def test_authorize_speaker_volume_and_fixed_commands(self):
        speaker=next(x for x in self.adapter.discover_candidates()['candidates'] if x['kind']=='speaker'); self.adapter.authorize_candidate(speaker['candidate_id']); s=next(x for x in self.adapter.list_devices()['devices'] if 'set_volume' in x['commands']); out=self.adapter.handle({'action':'control','device':s['device'],'command':'set_volume','value':30}); self.assertEqual(out['state']['volume_level'],0.3); self.assertTrue(self.router.services[-1][0].endswith('/media_player/volume_set'))
    def test_values_and_model_discovery_are_rejected(self):
        fan=next(x for x in self.adapter.discover_candidates()['candidates'] if x['kind']=='fan'); self.adapter.authorize_candidate(fan['candidate_id']); alias=next(x for x in self.adapter.list_devices()['devices'] if 'set_speed' in x['commands'])['device']
        for value in (-1,101,1.5,True):
            with self.assertRaises(HomeError): self.adapter.handle({'action':'control','device':alias,'command':'set_speed','value':value})
        for body in ({'action':'discover'},{'action':'authorize','candidate_id':'a'*24}):
            with self.assertRaises(HomeError): self.adapter.handle(body)
    def test_unknown_candidate(self):
        with self.assertRaises(HomeError) as caught: self.adapter.authorize_candidate('a'*24)
        self.assertEqual(caught.exception.code,'HOME_CANDIDATE_NOT_FOUND')
    def test_entity_without_device_id_remains_entity_scoped(self):
        self.states.append({"entity_id":"light.orphan","state":"off","attributes":{"friendly_name":"独立灯"}})
        disc=self.adapter.discover_candidates()['candidates']
        self.assertEqual(sum(1 for item in disc if item['kind']=='light'),1)

if __name__ == "__main__":
    unittest.main()
