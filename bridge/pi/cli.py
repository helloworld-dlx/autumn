import argparse,json,threading,tempfile,http.client
from dataclasses import replace
from pathlib import Path
from .auth import load_secret
from .config import BridgeConfig,load_config,validate_config,ACTIONS
from .runner_client import build_signed_request
from .server import create_server
from .file_pull import pull_file,cleanup_transfer,MAX_FILE_SIZE
DEFAULT_TRANSFER_ROOT=Path("/home/xyzlh/jarvis-bridge/transfers")
def doctor(c):
 try:validate_config(c);return True,{"loopback_only":True,"action_count_is_7":len(ACTIONS)==7,"config_valid":True}
 except ValueError:return False,{"config_valid":False}
def main(argv=None):
 p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True);s.add_parser("doctor");s.add_parser("selftest");s.add_parser("serve");x=s.add_parser("call");x.add_argument("--action",required=True);x.add_argument("--arguments-json",default="{}")
 fp=s.add_parser("file-pull");fp.add_argument("--path",required=True);fp.add_argument("--transfer-root",default=str(DEFAULT_TRANSFER_ROOT))
 fc=s.add_parser("file-cleanup");fc.add_argument("--transfer-id",required=True);fc.add_argument("--transfer-root",default=str(DEFAULT_TRANSFER_ROOT))
 a=p.parse_args(argv);c=load_config()
 if a.cmd=="doctor":ok,d=doctor(c);print(json.dumps(d));return 0 if ok else 1
 if a.cmd=="serve":
  try:load_secret(c.bridge_token_path);load_secret(c.runner_key_path);z=create_server(c)
  except (ValueError,OSError):return 1
  try:z.serve_forever()
  except KeyboardInterrupt:pass
  finally:z.server_close()
  return 0
 if a.cmd=="file-pull":
  ok,err=pull_file(a.path,c,transfer_root=Path(a.transfer_root))
  if ok is not None:print(json.dumps(ok));return 0
  print(json.dumps(err));return 1
 if a.cmd=="file-cleanup":
  ok,err=cleanup_transfer(a.transfer_id,Path(a.transfer_root))
  out={"status":"succeeded" if ok else "failed","transfer_id":a.transfer_id}
  if err:out.update(err)
  print(json.dumps(out));return 0 if ok else 1
 if a.cmd=="selftest":
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/".config"/"jarvis-bridge";root.mkdir(parents=True);k=root/"key";t=root/"token";k.write_bytes(b"k"*32);t.write_bytes(b"t"*32);test=replace(c,listen_port=0,runner_key_path=k,bridge_token_path=t);from .server import BridgeServer;z=BridgeServer(test);th=threading.Thread(target=z.serve_forever);th.start()
   try:
    x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("GET","/v1/health");ok=x.getresponse().status==200;x.close()
    x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST","/v1/execute",b'{"action":"system.ping","arguments":{}}',{"X-Jarvis-Bridge-Token":"bad"});bad=x.getresponse().status==401;x.close()
    from unittest.mock import patch
    with patch("jarvis_bridge.server.call_runner",return_value=(200,{"request_id":"mock","status":"success","output":{"ok":True},"error_code":None,"error_message":None})):
     x=http.client.HTTPConnection("127.0.0.1",z.server_address[1]);x.request("POST","/v1/execute",b'{"action":"system.ping","arguments":{}}',{"X-Jarvis-Bridge-Token":"t"*32});good=x.getresponse().status==200;x.close()
   finally:z.shutdown();z.server_close();th.join()
   return 0 if ok and bad and good and not th.is_alive() else 1
 try:v=json.loads(a.arguments_json);token=load_secret(c.bridge_token_path)
 except (ValueError,json.JSONDecodeError):return 1
 body=json.dumps({"action":a.action,"arguments":v}).encode();x=http.client.HTTPConnection("127.0.0.1",27901,timeout=8)
 try:x.request("POST","/v1/execute",body,{"Content-Type":"application/json","X-Jarvis-Bridge-Token":token.decode("utf-8")});r=x.getresponse();print(r.read().decode());return 0 if r.status==200 else 1
 finally:x.close()
if __name__=="__main__":raise SystemExit(main())
