import tempfile,unittest,json,http.client,threading
from pathlib import Path
from dataclasses import replace
from jarvis_bridge.config import BridgeConfig,validate_config,ACTIONS
from jarvis_bridge.auth import token_matches
from jarvis_bridge.runner_client import build_signed_request,canonical_payload,call_runner
from urllib.error import URLError
import socket
from jarvis_bridge.server import BridgeServer
from unittest.mock import patch
class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();p=Path(self.t.name);self.home=p/".config"/"jarvis-bridge";self.home.mkdir(parents=True);self.c=BridgeConfig(runner_key_path=self.home/"key",bridge_token_path=self.home/"token")
 def tearDown(self):self.t.cleanup()
 def test_config_and_actions(self):
  with patch("jarvis_bridge.config.HOME",self.home): validate_config(self.c)
  self.assertEqual(len(ACTIONS),5)
  for h in ("0.0.0.0","100.64.0.1","192.168.1.1"):
   with patch("jarvis_bridge.config.HOME",self.home):
    with self.assertRaises(ValueError):validate_config(replace(self.c,listen_host=h))
  with patch("jarvis_bridge.config.HOME",self.home):
   with self.assertRaises(ValueError):validate_config(replace(self.c,runner_base_url="http://8.8.8.8:27891"))
 def test_token_and_signature(self):
  self.assertTrue(token_matches("x"*32,b"x"*32));self.assertFalse(token_matches("x",b"x"*32))
  r=build_signed_request("system.ping",{},self.c,b"k"*32);self.assertEqual(len(r["signature"]),64);self.assertNotIn("signature",json.loads(canonical_payload(r)))
  q=build_signed_request("system.info",{},self.c,b"k"*32);self.assertNotEqual(r["signature"],q["signature"])
 def test_http_health_auth_and_execute(self):
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
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
 def test_timeout_and_unapproved_action(self):
  with patch("jarvis_bridge.runner_client.build_opener") as opener:
   for failure in (TimeoutError(),socket.timeout(),URLError(socket.timeout())):
    opener.return_value.open.side_effect=failure
    with self.assertRaisesRegex(RuntimeError,"RUNNER_TIMEOUT"):call_runner({},self.c)
  (self.home/"key").write_bytes(b"k"*32);(self.home/"token").write_bytes(b"t"*32);z=BridgeServer(replace(self.c,listen_port=0));thread=threading.Thread(target=z.serve_forever);thread.start()
  try:
   with patch("jarvis_bridge.server.call_runner") as runner:
    x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST","/v1/execute",b'{"action":"raw.command","arguments":{}}',{"X-Jarvis-Bridge-Token":"t"*32});r=x.getresponse();self.assertEqual(r.status,400);runner.assert_not_called();x.close()
  finally:z.shutdown();z.server_close();thread.join()
