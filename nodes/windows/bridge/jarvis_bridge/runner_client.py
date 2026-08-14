import hashlib,hmac,json,secrets,uuid
from datetime import datetime,timedelta,timezone
import socket
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from .config import ACTIONS
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args):return None
def canonical_payload(r):return json.dumps({k:v for k,v in r.items() if k!="signature"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def build_signed_request(action,arguments,c,key):
 if action not in ACTIONS or not isinstance(arguments,dict):raise ValueError("ACTION_NOT_ALLOWED")
 now=datetime.now(timezone.utc);r={"protocol_version":"1.0","request_id":str(uuid.uuid4()),"target_device":c.runner_target_device,"action":action,"arguments":arguments,"issued_at":now.isoformat(),"expires_at":(now+timedelta(seconds=60)).isoformat(),"nonce":secrets.token_urlsafe(24),"key_id":c.runner_key_id};r["signature"]=hmac.new(key,canonical_payload(r),hashlib.sha256).hexdigest();return r
def call_runner(r,c):
 body=json.dumps(r,ensure_ascii=False,separators=(",",":")).encode();q=Request(c.runner_base_url+"/v1/task",body,{"Content-Type":"application/json"},method="POST")
 try:
  with build_opener(ProxyHandler({}),NoRedirect()).open(q,timeout=c.request_timeout_seconds) as x:return x.status,json.loads(x.read().decode())
 except HTTPError as e:
  try:return e.code,json.loads(e.read().decode())
  except Exception:return e.code,{}
 except (TimeoutError,socket.timeout):raise RuntimeError("RUNNER_TIMEOUT")
 except URLError as e:
  reason=e.reason
  if isinstance(reason,(TimeoutError,socket.timeout)) or getattr(reason,"errno",None) in (110,10060):raise RuntimeError("RUNNER_TIMEOUT")
  raise RuntimeError("RUNNER_OFFLINE")
