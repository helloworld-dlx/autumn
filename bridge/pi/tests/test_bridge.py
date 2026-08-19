import tempfile,unittest,json,http.client,threading
from pathlib import Path
from dataclasses import replace
from jarvis_bridge.config import BridgeConfig,validate_config,ACTIONS
from jarvis_bridge.auth import token_matches
from jarvis_bridge.runner_client import build_signed_request,canonical_payload,call_runner
from urllib.error import URLError
import socket
from jarvis_bridge.server import BridgeServer
from jarvis_bridge.file_pull import publish_text_artifact
from jarvis_bridge.node_registry import NodeRegistry,PI5_CORE,WINDOWS_MAIN,XIAOMI15,WINDOWS_HEALTH_TTL
from unittest.mock import patch,ANY

EXPECTED_ACTIONS = (
    "system.ping",
    "system.info",
    "system.status",
    "files.list_directory",
    "files.search",
    "program.list",
    "program.run",
)
class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();p=Path(self.t.name);self.home=p/".config"/"jarvis-bridge";self.home.mkdir(parents=True);self.c=BridgeConfig(runner_key_path=self.home/"key",bridge_token_path=self.home/"token")
 def tearDown(self):self.t.cleanup()
 def test_01_actions_are_exactly_seven(self):
  # 1) ACTIONS 恰好为上述 7 个
  self.assertEqual(ACTIONS, EXPECTED_ACTIONS)
  self.assertEqual(len(ACTIONS), 7)
 def test_02_doctor_reports_action_count_is_7(self):
  # 2) doctor 验证 action_count_is_7，且严格校验 len(ACTIONS) == 7
  from jarvis_bridge.cli import doctor
  with patch("jarvis_bridge.config.HOME", self.home):
   ok, d = doctor(self.c)
  self.assertTrue(ok)
  self.assertIn("action_count_is_7", d)
  self.assertTrue(d["action_count_is_7"])
  self.assertNotIn("action_count_is_5", d)
  self.assertTrue(d["config_valid"])
  self.assertEqual(len(ACTIONS), 7)
 def test_config_loopback_and_runner_url(self):
  with patch("jarvis_bridge.config.HOME",self.home): validate_config(self.c)
  for h in ("0.0.0.0","100.64.0.1","192.168.1.1"):
   with patch("jarvis_bridge.config.HOME",self.home):
    with self.assertRaises(ValueError):validate_config(replace(self.c,listen_host=h))
  with patch("jarvis_bridge.config.HOME",self.home):
   with self.assertRaises(ValueError):validate_config(replace(self.c,runner_base_url="http://8.8.8.8:27891"))
 def test_token_and_signature(self):
  self.assertTrue(token_matches("x"*32,b"x"*32));self.assertFalse(token_matches("x",b"x"*32))
  r=build_signed_request("system.ping",{},self.c,b"k"*32);self.assertEqual(len(r["signature"]),64);self.assertNotIn("signature",json.loads(canonical_payload(r)))
  q=build_signed_request("system.info",{},self.c,b"k"*32);self.assertNotEqual(r["signature"],q["signature"])
 def test_03_04_build_signed_request_accepts_program_actions(self):
  # 3) build_signed_request 接受 program.list + {}
  # 4) build_signed_request 接受 program.run + {"program_id":"hello_jarvis"}，且 program_id 原样进入签名请求
  r_list = build_signed_request("program.list", {}, self.c, b"k"*32)
  self.assertEqual(r_list["action"], "program.list")
  self.assertEqual(r_list["arguments"], {})
  self.assertEqual(len(r_list["signature"]), 64)
  payload_list = json.loads(canonical_payload(r_list))
  self.assertEqual(payload_list["action"], "program.list")
  self.assertEqual(payload_list["arguments"], {})
  r_run = build_signed_request("program.run", {"program_id": "hello_jarvis"}, self.c, b"k"*32)
  self.assertEqual(r_run["action"], "program.run")
  self.assertEqual(r_run["arguments"], {"program_id": "hello_jarvis"})
  self.assertEqual(len(r_run["signature"]), 64)
  payload_run = json.loads(canonical_payload(r_run))
  self.assertEqual(payload_run["action"], "program.run")
  self.assertEqual(payload_run["arguments"], {"program_id": "hello_jarvis"})
  # 不同 program_id 必须得到不同签名
  r_run_other = build_signed_request("program.run", {"program_id": "another"}, self.c, b"k"*32)
  self.assertNotEqual(r_run["signature"], r_run_other["signature"])
 def test_http_health_auth_and_execute(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0),start_probe=False);thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(method,path,body=None,token=None):
   h={};
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request(method,path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   self.assertEqual(call("GET","/v1/health")[0],200)
   with patch("jarvis_bridge.server.call_runner") as runner:
    self.assertEqual(call("POST","/v1/execute",b'{"action":"system.ping","arguments":{}}')[0],401);runner.assert_not_called()
    runner.return_value=(200,{"request_id":"r","status":"success","output":{"ok":True},"error_code":None,"error_message":None})
    self.assertEqual(call("POST","/v1/execute",b'{"action":"system.ping","arguments":{}}',"t"*32)[0],200);runner.assert_called_once()
  finally:z.shutdown();z.server_close();thread.join()
 def test_windows_probe_registers_touches_and_recovers(self):
  from datetime import timedelta
  z=BridgeServer(replace(self.c,listen_port=0),start_probe=False)
  try:
   self.assertEqual(z.registry.get("windows-main")["online"],"UNKNOWN")
   self.assertEqual(z.registry.get("xiaomi15")["online"],"UNKNOWN")
   with patch("jarvis_bridge.server.runner_health",return_value=True):
    self.assertTrue(z.probe_windows_once());first=z.registry.get("windows-main")
    self.assertEqual(first["capabilities"],WINDOWS_MAIN["capabilities"]);self.assertEqual(first["online"],"ONLINE")
    self.assertTrue(z.probe_windows_once());self.assertEqual(z.registry.get("windows-main")["online"],"ONLINE")
   z.registry.upsert({**WINDOWS_MAIN,"last_seen":(z.registry._clock()-WINDOWS_HEALTH_TTL-timedelta(seconds=1)).isoformat()})
   with patch("jarvis_bridge.server.runner_health",return_value=False):self.assertFalse(z.probe_windows_once())
   self.assertEqual(z.registry.get("windows-main")["online"],"OFFLINE")
   with patch("jarvis_bridge.server.runner_health",return_value=True):self.assertTrue(z.probe_windows_once())
   self.assertEqual(z.registry.get("windows-main")["online"],"ONLINE")
  finally:z.server_close()
 def test_internal_phone_touch_is_fixed_and_not_a_generic_registration_api(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0),start_probe=False);thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(path,body=None):
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST",path,body);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   self.assertEqual(z.registry.get("xiaomi15")["online"],"UNKNOWN")
   status,_=call("/v1/internal/nodes/xiaomi15/touch");self.assertEqual(status,200);node=z.registry.get("xiaomi15")
   self.assertEqual(node["capabilities"],XIAOMI15["capabilities"]);self.assertIn("camera.capture",node["capabilities"]);self.assertEqual(node["node_version"],"companion-pwa-v19");self.assertEqual(node["online"],"RECENT")
   status,error=call("/v1/internal/nodes/other/touch");self.assertEqual(status,404);self.assertEqual(error["error_code"],"NOT_FOUND")
   status,error=call("/v1/internal/nodes/xiaomi15/touch",b"{}");self.assertEqual(status,400);self.assertEqual(error["error_code"],"BRIDGE_REQUEST_INVALID")
  finally:z.shutdown();z.server_close();thread.join()
 def test_home_route_requires_bridge_token_and_forwards_safe_body(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0),start_probe=False);thread=threading.Thread(target=z.serve_forever);thread.start()
  calls=[];z.home.handle=lambda body:calls.append(body) or {"status":"OK","devices":[{"device":"desk_lamp","label":"Desk Lamp"}]}
  try:
   body=json.dumps({"action":"list"}).encode();x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST","/v1/home",body=body,headers={"Content-Type":"application/json"});r=x.getresponse();self.assertEqual(r.status,401);r.read();x.close()
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST","/v1/home",body=body,headers={"Content-Type":"application/json","X-Jarvis-Bridge-Token":"t"*32});r=x.getresponse();payload=json.loads(r.read());x.close();self.assertEqual(r.status,200);self.assertEqual(calls,[{"action":"list"}]);self.assertNotIn("entity_id",json.dumps(payload))
  finally:z.shutdown();z.server_close();thread.join()
 def test_node_registry_valid_pi5_descriptor_get_list_touch_and_presence(self):
  from datetime import datetime,timezone,timedelta
  now=datetime(2026,8,14,tzinfo=timezone.utc);registry=NodeRegistry(clock=lambda:now)
  node=registry.upsert({**PI5_CORE,"last_seen":None})
  self.assertEqual(node["node_id"],"pi5-core");self.assertEqual(node["protocol_version"],"1");self.assertEqual(node["online"],"ONLINE")
  self.assertEqual(registry.list(),[node]);self.assertEqual(registry.touch("pi5-core")["last_seen"],"2026-08-14T00:00:00Z")
  self.assertEqual(registry.derive_presence("core",now-timedelta(days=30)),"ONLINE")
  self.assertEqual(registry.derive_presence("phone",now-timedelta(seconds=91)),"RECENT")
  self.assertEqual(registry.derive_presence("phone",now-timedelta(minutes=11)),"UNKNOWN")
  known=registry.register_known(XIAOMI15);self.assertEqual(known["online"],"UNKNOWN");self.assertIsNone(registry.get("xiaomi15")["last_seen"])
 def test_node_registry_rejects_unknown_and_private_fields(self):
  registry=NodeRegistry()
  with self.assertRaises(ValueError):registry.upsert({**PI5_CORE,"last_seen":None,"token":"forbidden"})
  with self.assertRaises(ValueError):registry.upsert({**PI5_CORE,"last_seen":None,"metadata":{"conversation":"private"}})
  self.assertIsNone(registry.get("missing"))
 def test_node_endpoints_are_safe_and_unknown_is_404(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(path):
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("GET",path);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   status,nodes=call("/v1/nodes");self.assertEqual(status,200);self.assertEqual(nodes["nodes"][0]["node_id"],"pi5-core");self.assertNotIn("token",json.dumps(nodes))
   status,node=call("/v1/nodes/pi5-core");self.assertEqual(status,200);self.assertEqual(node["capabilities"],PI5_CORE["capabilities"])
   status,error=call("/v1/nodes/missing");self.assertEqual(status,404);self.assertEqual(error["error_code"],"NOT_FOUND")
  finally:z.shutdown();z.server_close();thread.join()

 def test_companion_generated_text_artifact_is_bounded_and_download_ready(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)/"transfers"
   result,error=publish_text_artifact("桶形移位器学习笔记.md","# 桶形移位器\n\nhello",transfer_root=root)
   self.assertIsNone(error);self.assertEqual(result["status"],"succeeded")
   folder=root/result["transfer_id"]
   self.assertEqual((folder/"data.bin").read_text("utf-8"),"# 桶形移位器\n\nhello")
   meta=json.loads((folder/"meta.json").read_text("utf-8"));self.assertEqual(meta["filename"],"桶形移位器学习笔记.md");self.assertEqual(meta["source"],"companion-generated-text")
   bad,error=publish_text_artifact("../secret.md","x",transfer_root=root);self.assertIsNone(bad);self.assertEqual(error["error_code"],"ARTIFACT_FILENAME_INVALID")
   bad,error=publish_text_artifact("unsafe.bin","x",transfer_root=root);self.assertIsNone(bad);self.assertEqual(error["error_code"],"ARTIFACT_TYPE_NOT_ALLOWED")

 def test_companion_publish_text_endpoint_is_token_authenticated(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32)
  z=BridgeServer(replace(self.c,listen_port=0),start_probe=False);thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(token):
   body=json.dumps({"filename":"note.md","content":"hello"},ensure_ascii=False).encode();h={"Content-Type":"application/json"}
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST","/v1/files/publish-text",body,h);r=x.getresponse();payload=json.loads(r.read());x.close();return r.status,payload
  try:
   self.assertEqual(call(None)[0],401)
   with patch("jarvis_bridge.server.DEFAULT_TRANSFER_ROOT",Path(self.t.name)/"published"):
    status,payload=call("t"*32);self.assertEqual(status,200);self.assertEqual(payload["filename"],"note.md");self.assertEqual(payload["status"],"succeeded")
  finally:z.shutdown();z.server_close();thread.join()

 def test_companion_status_is_loopback_read_model_and_sanitized(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32)
  z=BridgeServer(replace(self.c,listen_port=0),start_probe=False);thread=threading.Thread(target=z.serve_forever);thread.start()
  try:
   with patch("jarvis_bridge.server.job_list",return_value=(200,{"status":"success","output":{"jobs":[{"job_id":"j1","status":"running"}]}})), \
        patch("jarvis_bridge.server.authorization_list",return_value=(200,{"status":"success","output":{"authorizations":[{"authorization_request_id":"a1","task":"write docs","workspace":"autumn"}]}})), \
        patch("jarvis_bridge.server.worker_control_status",return_value=(200,{"status":"success","output":{"workers_paused":False}})):
    x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("GET","/v1/internal/companion/status");r=x.getresponse();payload=json.loads(r.read());x.close()
   self.assertEqual(r.status,200)
   self.assertTrue(payload["windowsDataAvailable"]);self.assertFalse(payload["workersPaused"])
   self.assertEqual(payload["jobs"][0]["job_id"],"j1");self.assertEqual(payload["approvals"][0]["workspace"],"autumn")
   self.assertIn("pi5-core",[node["node_id"] for node in payload["nodes"]])
   statuses={node["node_id"]:node["online"] for node in payload["nodes"]}
   self.assertEqual(statuses["pi5-core"],"ONLINE")
   self.assertEqual(statuses["windows-main"],"ONLINE")
   self.assertNotIn("token",json.dumps(payload))
  finally:z.shutdown();z.server_close();thread.join()

 def test_companion_status_marks_windows_online_on_transport_response_even_if_data_is_unavailable(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32)
  z=BridgeServer(replace(self.c,listen_port=0),start_probe=False);thread=threading.Thread(target=z.serve_forever);thread.start()
  try:
   with patch("jarvis_bridge.server.job_list",return_value=(503,{"status":"failed","output":{}})), \
        patch("jarvis_bridge.server.authorization_list",return_value=(503,{"status":"failed","output":{}})), \
        patch("jarvis_bridge.server.worker_control_status",return_value=(503,{"status":"failed","output":{}})):
    x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("GET","/v1/internal/companion/status");r=x.getresponse();payload=json.loads(r.read());x.close()
   self.assertEqual(r.status,200);self.assertFalse(payload["windowsDataAvailable"])
   statuses={node["node_id"]:node["online"] for node in payload["nodes"]}
   self.assertEqual(statuses["pi5-core"],"ONLINE");self.assertEqual(statuses["windows-main"],"ONLINE")
  finally:z.shutdown();z.server_close();thread.join()

 def test_companion_file_pull_requires_token_and_never_returns_local_path(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32)
  z=BridgeServer(replace(self.c,listen_port=0),start_probe=False);thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(token=None):
   headers={"Content-Type":"application/json"}
   if token: headers["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST","/v1/files/pull",json.dumps({"path":"D:\\docs\\report.pdf"}).encode(),headers);r=x.getresponse();payload=json.loads(r.read());x.close();return r.status,payload
  try:
   with patch("jarvis_bridge.server.pull_file",return_value=({"status":"succeeded","transfer_id":"abcdefghijklmnop","local_path":"/private/data.bin","filename":"report.pdf","size":5,"sha256":"abc"},None)) as pull:
    self.assertEqual(call()[0],401)
    status,payload=call("t"*32)
    self.assertEqual(status,200);self.assertEqual(payload["filename"],"report.pdf");self.assertNotIn("local_path",payload)
    pull.assert_called_once()
  finally:z.shutdown();z.server_close();thread.join()

 def test_05_06_bridge_http_accepts_program_actions(self):
  # 5) Bridge HTTP 接受 program.list
  # 6) Bridge HTTP 接受 program.run
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(method,path,body=None,token=None):
   h={};
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request(method,path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   with patch("jarvis_bridge.server.call_runner") as runner:
    runner.return_value = (200, {"request_id":"r","status":"success","output":{"programs":[]},"error_code":None,"error_message":None})
    s_list, _ = call("POST","/v1/execute",b'{"action":"program.list","arguments":{}}',"t"*32)
    self.assertEqual(s_list, 200)
    self.assertEqual(runner.call_count, 1)
    # 检查签名请求中 action 正确，arguments 原样透传
    signed = runner.call_args.args[0]
    self.assertEqual(signed["action"], "program.list")
    self.assertEqual(signed["arguments"], {})
    runner.return_value = (200, {"request_id":"r2","status":"success","output":{"exit_code":0},"error_code":None,"error_message":None})
    s_run, _ = call("POST","/v1/execute",b'{"action":"program.run","arguments":{"program_id":"hello_jarvis"}}',"t"*32)
    self.assertEqual(s_run, 200)
    self.assertEqual(runner.call_count, 2)
    signed_run = runner.call_args.args[0]
    self.assertEqual(signed_run["action"], "program.run")
    self.assertEqual(signed_run["arguments"], {"program_id":"hello_jarvis"})
  finally:z.shutdown();z.server_close();thread.join()
 def test_07_08_raw_command_and_unknown_action_rejected(self):
  # 7) raw.command 仍在 Bridge 层被拒绝（400，runner 不被调用）
  # 8) 未登记 action 仍被拒绝
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(method,path,body=None,token=None):
   h={};
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request(method,path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   with patch("jarvis_bridge.server.call_runner") as runner:
    s_bad, v_bad = call("POST","/v1/execute",b'{"action":"raw.command","arguments":{"cmd":"ls"}}',"t"*32)
    self.assertEqual(s_bad, 400)
    self.assertEqual(v_bad["error_code"], "ACTION_NOT_ALLOWED")
    runner.assert_not_called()
    s_unk, v_unk = call("POST","/v1/execute",b'{"action":"system.shutdown","arguments":{}}',"t"*32)
    self.assertEqual(s_unk, 400)
    self.assertEqual(v_unk["error_code"], "ACTION_NOT_ALLOWED")
    runner.assert_not_called()
  finally:z.shutdown();z.server_close();thread.join()
 def test_09_program_run_not_auto_retried(self):
  # 9) program.run 不会被自动重试：runner mock 抛超时，Bridge 必须把 RUNNER_TIMEOUT 直接返回，不重试
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(method,path,body=None,token=None):
   h={};
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request(method,path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   with patch("jarvis_bridge.server.call_runner") as runner:
    from urllib.error import URLError
    runner.side_effect = RuntimeError("RUNNER_TIMEOUT")
    s, v = call("POST","/v1/execute",b'{"action":"program.run","arguments":{"program_id":"hello_jarvis"}}',"t"*32)
    self.assertEqual(s, 503)
    self.assertEqual(v["error_code"], "RUNNER_TIMEOUT")
    self.assertEqual(runner.call_count, 1, "program.run must not be retried")
  finally:z.shutdown();z.server_close();thread.join()
 def test_10_existing_auth_timeout_offline(self):
  # 10) 原有认证、超时和离线测试继续通过
  with patch("jarvis_bridge.runner_client.build_opener") as opener:
   for failure in (TimeoutError(),socket.timeout(),URLError(socket.timeout())):
    opener.return_value.open.side_effect=failure
    with self.assertRaisesRegex(RuntimeError,"RUNNER_TIMEOUT"):call_runner({},self.c)
   for failure in (URLError("connection refused"),):
    opener.return_value.open.side_effect=failure
    with self.assertRaisesRegex(RuntimeError,"RUNNER_OFFLINE"):call_runner({},self.c)
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(method,path,body=None,token=None):
   h={};
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request(method,path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   self.assertEqual(call("GET","/v1/health")[0],200)
   self.assertEqual(call("POST","/v1/execute",b'{"action":"system.ping","arguments":{}}')[0],401)
   with patch("jarvis_bridge.server.call_runner") as runner:
    runner.return_value=(200,{"request_id":"r","status":"success","output":{"ok":True},"error_code":None,"error_message":None})
    self.assertEqual(call("POST","/v1/execute",b'{"action":"system.ping","arguments":{}}',"t"*32)[0],200)
  finally:z.shutdown();z.server_close();thread.join()
 def test_11_job_routes_require_auth(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(path,body=None,token=None):
   h={}
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST",path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   for path in ("/v1/jobs/submit","/v1/jobs/status","/v1/jobs/cancel","/v1/jobs/result"):
    self.assertEqual(call(path,b'{}')[0],401)
  finally:z.shutdown();z.server_close();thread.join()
 def test_12_job_routes_forward_correctly(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(path,body=None,token=None):
   h={}
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST",path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   with patch("jarvis_bridge.server.submit_job") as sj,patch("jarvis_bridge.server.job_status") as js,patch("jarvis_bridge.server.cancel_job") as cj,patch("jarvis_bridge.server.job_result") as jr:
    sj.return_value=(200,{"request_id":"r1","status":"queued","output":{"job_id":"j1"},"error_code":None,"error_message":None})
    s,v=call("/v1/jobs/submit",b'{"operation":"archive.list","archive_path":"D:\\test"}',"t"*32)
    self.assertEqual(s,200);sj.assert_called_once();js.assert_not_called();self.assertEqual(v["result"]["job_id"],"j1")
    js.return_value=(200,{"request_id":"r2","status":"running","output":{},"error_code":None,"error_message":None})
    s,v=call("/v1/jobs/status",b'{"job_id":"j1"}',"t"*32)
    self.assertEqual(s,200);js.assert_called_once_with("j1",z.config,ANY);self.assertEqual(v["status"],"running")
    cj.return_value=(200,{"request_id":"r3","status":"cancelled","output":{},"error_code":None,"error_message":None})
    s,v=call("/v1/jobs/cancel",b'{"job_id":"j1"}',"t"*32)
    self.assertEqual(s,200);cj.assert_called_once_with("j1",z.config,ANY);self.assertEqual(v["status"],"cancelled")
    jr.return_value=(200,{"request_id":"r4","status":"success","output":{"files":[]},"error_code":None,"error_message":None})
    s,v=call("/v1/jobs/result",b'{"job_id":"j1"}',"t"*32)
    self.assertEqual(s,200);jr.assert_called_once_with("j1",z.config,ANY);self.assertEqual(v["status"],"success")
  finally:z.shutdown();z.server_close();thread.join()
 def test_13_job_routes_runner_offline_normalized(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(path,body=None,token=None):
   h={}
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST",path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   with patch("jarvis_bridge.server.submit_job") as sj:
    sj.side_effect=RuntimeError("RUNNER_OFFLINE")
    s,v=call("/v1/jobs/submit",b'{"operation":"archive.list","archive_path":"D:\\test"}',"t"*32)
    self.assertEqual(s,503);self.assertEqual(v["error_code"],"RUNNER_OFFLINE")
  finally:z.shutdown();z.server_close();thread.join()
 def test_14_legacy_execute_still_works(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  def call(method,path,body=None,token=None):
   h={}
   if token:h["X-Jarvis-Bridge-Token"]=token
   x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request(method,path,body,h);r=x.getresponse();v=json.loads(r.read());x.close();return r.status,v
  try:
   with patch("jarvis_bridge.server.call_runner") as runner:
    runner.return_value=(200,{"request_id":"r","status":"success","output":{"ok":True},"error_code":None,"error_message":None})
    self.assertEqual(call("POST","/v1/execute",b'{"action":"system.ping","arguments":{}}',"t"*32)[0],200)
    runner.return_value=(200,{"request_id":"r2","status":"success","output":{"exit_code":0},"error_code":None,"error_message":None})
    self.assertEqual(call("POST","/v1/execute",b'{"action":"program.run","arguments":{"program_id":"hello_jarvis"}}',"t"*32)[0],200)
  finally:z.shutdown();z.server_close();thread.join()
if __name__ == "__main__":
 unittest.main()
