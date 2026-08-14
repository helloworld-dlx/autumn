import json,uuid,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from .auth import load_secret,token_matches
from .config import ACTIONS,validate_config
from .runner_client import build_signed_request,call_runner,submit_job,job_status,cancel_job,job_result,authorization_request,authorization_approve,worker_control_status,worker_pause,worker_resume,runner_health
from .node_registry import NodeRegistry,PI5_CORE,WINDOWS_MAIN,XIAOMI15
PROBE_INTERVAL_SECONDS=30
class BridgeServer(ThreadingHTTPServer):
 daemon_threads=True;request_queue_size=8
 def __init__(self,c,start_probe=False):
  self.config=c;self.registry=NodeRegistry();self.registry.upsert({**PI5_CORE,"last_seen":None});self._probe_stop=threading.Event();self._probe_thread=None;super().__init__((c.listen_host,c.listen_port),Handler)
  if start_probe:
   self._probe_thread=threading.Thread(target=self._probe_loop,name="windows-node-probe",daemon=True);self._probe_thread.start()
 def get_request(self):x,a=super().get_request();x.settimeout(15);return x,a
 def probe_windows_once(self):
  if not runner_health(self.config):return False
  if self.registry.get("windows-main") is None:self.registry.upsert({**WINDOWS_MAIN,"last_seen":None})
  else:self.registry.touch("windows-main")
  return True
 def _probe_loop(self):
  while not self._probe_stop.is_set():
   self.probe_windows_once();self._probe_stop.wait(PROBE_INTERVAL_SECONDS)
 def shutdown(self):
  self._probe_stop.set();super().shutdown()
  if self._probe_thread:self._probe_thread.join(timeout=4)
class Handler(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1";server_version="jarvis-bridge";sys_version=""
 def log_message(self,*args):pass
 def send(self,s,b):
  d=json.dumps(b,separators=(",",":"),ensure_ascii=False).encode();self.send_response(s);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(d)));self.send_header("Connection","close");self.end_headers();self.wfile.write(d);self.close_connection=True
 def error(self,s,c):self.send(s,{"bridge_request_id":None,"runner_request_id":None,"status":"rejected","result":{},"error_code":c,"message":"request rejected"})
 def _parse_request_path(self):
  p=urlsplit(self.path)
  if p.query:self.error(400,"BRIDGE_REQUEST_INVALID");return None
  return p.path
 def do_GET(self):
  p=self._parse_request_path()
  if p=="/v1/health":self.send(200,{"status":"ok","bridge":"jarvis-bridge","protocol_version":"1.0"})
  elif p=="/v1/nodes":self.send(200,{"nodes":self.server.registry.list()})
  elif p and p.startswith("/v1/nodes/"):
   node_id=p.removeprefix("/v1/nodes/")
   if not node_id or "/" in node_id:self.error(404,"NOT_FOUND")
   else:
    node=self.server.registry.get(node_id)
    if node is None:self.error(404,"NOT_FOUND")
    else:self.send(200,node)
  elif p=="/v1/execute":self.error(405,"METHOD_NOT_ALLOWED")
  elif p:self.error(404,"NOT_FOUND")
 def do_POST(self):
  p=self._parse_request_path()
  if p=="/v1/health":self.error(405,"METHOD_NOT_ALLOWED");return
  if p=="/v1/internal/nodes/xiaomi15/touch":
   if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length") not in (None,"0"):self.error(400,"BRIDGE_REQUEST_INVALID");return
   if self.server.registry.get("xiaomi15") is None:self.server.registry.upsert({**XIAOMI15,"last_seen":None})
   else:self.server.registry.touch("xiaomi15")
   self.send(200,{"status":"ok"});return
  # Job routes — separate namespace, no ACTIONS check
  if p in ("/v1/jobs/submit","/v1/jobs/status","/v1/jobs/cancel","/v1/jobs/result"):
   self._do_job(p);return
  # Phase 2B-4E2: Authorization routes — stateless passthrough, no ACTIONS check
  if p in ("/v1/authorizations/request","/v1/authorizations/approve"):
   self._do_authorization(p);return
  # Phase 2B-5B: Worker control routes — stateless passthrough, no ACTIONS check
  if p in ("/v1/workers/status","/v1/workers/pause","/v1/workers/resume"):
   self._do_worker_control(p);return
  if p!="/v1/execute":self.error(404,"NOT_FOUND");return
  self._do_execute()
 def _do_execute(self):
  try:t=load_secret(self.server.config.bridge_token_path)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  if not token_matches(self.headers.get("X-Jarvis-Bridge-Token"),t):self.error(401,"BRIDGE_AUTH_FAILED");return
  n=self.headers.get("Content-Length")
  if self.headers.get("Transfer-Encoding") or not n or not n.isdecimal() or not 0<int(n)<=self.server.config.maximum_request_body_bytes:self.error(400,"BRIDGE_REQUEST_INVALID");return
  try:v=json.loads(self.rfile.read(int(n)).decode())
  except Exception:self.error(400,"BRIDGE_REQUEST_INVALID");return
  if not isinstance(v,dict) or set(v)!={"action","arguments"} or v["action"] not in ACTIONS or not isinstance(v["arguments"],dict):self.error(400,"ACTION_NOT_ALLOWED");return
  bid=str(uuid.uuid4())
  try:r=build_signed_request(v["action"],v["arguments"],self.server.config,load_secret(self.server.config.runner_key_path));_,out=call_runner(r,self.server.config)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  except RuntimeError as e:self.send(503,{"bridge_request_id":bid,"runner_request_id":None,"status":"failed","result":{},"error_code":str(e),"message":"runner unavailable"});return
  self.send(200,{"bridge_request_id":bid,"runner_request_id":out.get("request_id"),"status":out.get("status","failed"),"result":out.get("output",{}),"error_code":out.get("error_code"),"message":out.get("error_message")})
 def _do_job(self,path):
  try:t=load_secret(self.server.config.bridge_token_path)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  if not token_matches(self.headers.get("X-Jarvis-Bridge-Token"),t):self.error(401,"BRIDGE_AUTH_FAILED");return
  n=self.headers.get("Content-Length")
  if self.headers.get("Transfer-Encoding") or not n or not n.isdecimal() or not 0<int(n)<=self.server.config.maximum_request_body_bytes:self.error(400,"BRIDGE_REQUEST_INVALID");return
  try:body=json.loads(self.rfile.read(int(n)).decode())
  except Exception:self.error(400,"BRIDGE_REQUEST_INVALID");return
  if not isinstance(body,dict):self.error(400,"BRIDGE_REQUEST_INVALID");return
  bid=str(uuid.uuid4())
  try:key=load_secret(self.server.config.runner_key_path)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  try:
   if path=="/v1/jobs/submit":
    _,out=submit_job(body,self.server.config,key)
   elif path=="/v1/jobs/status":
    _,out=job_status(body.get("job_id",""),self.server.config,key)
   elif path=="/v1/jobs/cancel":
    _,out=cancel_job(body.get("job_id",""),self.server.config,key)
   elif path=="/v1/jobs/result":
    _,out=job_result(body.get("job_id",""),self.server.config,key)
   else:self.error(404,"NOT_FOUND");return
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  except RuntimeError as e:self.send(503,{"bridge_request_id":bid,"runner_request_id":None,"status":"failed","result":{},"error_code":str(e),"message":"runner unavailable"});return
  self.send(200,{"bridge_request_id":bid,"runner_request_id":out.get("request_id"),"status":out.get("status","failed"),"result":out.get("output",{}),"error_code":out.get("error_code"),"message":out.get("error_message")})

 # Phase 2B-4E2: Authorization passthrough — stateless, no local state
 def _do_authorization(self,path):
  try:t=load_secret(self.server.config.bridge_token_path)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  if not token_matches(self.headers.get("X-Jarvis-Bridge-Token"),t):self.error(401,"BRIDGE_AUTH_FAILED");return
  n=self.headers.get("Content-Length")
  if self.headers.get("Transfer-Encoding") or not n or not n.isdecimal() or not 0<int(n)<=self.server.config.maximum_request_body_bytes:self.error(400,"BRIDGE_REQUEST_INVALID");return
  try:body=json.loads(self.rfile.read(int(n)).decode())
  except Exception:self.error(400,"BRIDGE_REQUEST_INVALID");return
  if not isinstance(body,dict):self.error(400,"BRIDGE_REQUEST_INVALID");return
  bid=str(uuid.uuid4())
  try:key=load_secret(self.server.config.runner_key_path)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  try:
   if path=="/v1/authorizations/request":
    _,out=authorization_request(body.get("task",""),body.get("real_workspace",""),self.server.config,key)
   elif path=="/v1/authorizations/approve":
    _,out=authorization_approve(body.get("authorization_request_id",""),self.server.config,key)
   else:self.error(404,"NOT_FOUND");return
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  except RuntimeError as e:self.send(503,{"bridge_request_id":bid,"runner_request_id":None,"status":"failed","result":{},"error_code":str(e),"message":"runner unavailable"});return
  self.send(200,{"bridge_request_id":bid,"runner_request_id":out.get("request_id"),"status":out.get("status","failed"),"result":out.get("output",{}),"error_code":out.get("error_code"),"message":out.get("error_message")})

 # Phase 2B-5B: Worker control passthrough — stateless, no local state
 def _do_worker_control(self,path):
  try:t=load_secret(self.server.config.bridge_token_path)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  if not token_matches(self.headers.get("X-Jarvis-Bridge-Token"),t):self.error(401,"BRIDGE_AUTH_FAILED");return
  n=self.headers.get("Content-Length")
  if self.headers.get("Transfer-Encoding") or not n or not n.isdecimal() or not 0<int(n)<=self.server.config.maximum_request_body_bytes:self.error(400,"BRIDGE_REQUEST_INVALID");return
  try:body=json.loads(self.rfile.read(int(n)).decode())
  except Exception:self.error(400,"BRIDGE_REQUEST_INVALID");return
  if not isinstance(body,dict):self.error(400,"BRIDGE_REQUEST_INVALID");return
  bid=str(uuid.uuid4())
  try:key=load_secret(self.server.config.runner_key_path)
  except ValueError:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  try:
   if path=="/v1/workers/status":
    _,out=worker_control_status(self.server.config,key)
   elif path=="/v1/workers/pause":
    _,out=worker_pause(self.server.config,key)
   elif path=="/v1/workers/resume":
    _,out=worker_resume(self.server.config,key)
   else:self.error(404,"NOT_FOUND");return
  except ValueError as e:self.error(503,"BRIDGE_KEY_UNAVAILABLE");return
  except RuntimeError as e:self.send(503,{"bridge_request_id":bid,"runner_request_id":None,"status":"failed","result":{},"error_code":str(e),"message":"runner unavailable"});return
  self.send(200,{"bridge_request_id":bid,"runner_request_id":out.get("request_id"),"status":out.get("status","failed"),"result":out.get("output",{}),"error_code":out.get("error_code"),"message":out.get("error_message")})

 def do_PUT(self):self.error(405,"METHOD_NOT_ALLOWED")
 def send_error(self,code,*args):self.error(405,"METHOD_NOT_ALLOWED")
def create_server(c):validate_config(c);return BridgeServer(c,start_probe=True)
