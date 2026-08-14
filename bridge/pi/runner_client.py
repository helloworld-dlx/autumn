import hashlib,hmac,json,secrets,uuid
from datetime import datetime,timedelta,timezone
import socket
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from .config import ACTIONS
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args):return None
def runner_health(c,timeout_seconds=3):
 q=Request(c.runner_base_url+"/v1/health",method="GET")
 try:
  with build_opener(ProxyHandler({}),NoRedirect()).open(q,timeout=timeout_seconds) as x:
   return x.status==200 and json.loads(x.read().decode())=={"status":"ok","protocol_version":"1.0","runner":"jarvis-windows-runner"}
 except (HTTPError,URLError,TimeoutError,socket.timeout,ValueError,json.JSONDecodeError):return False
def canonical_payload(r):return json.dumps({k:v for k,v in r.items() if k!="signature"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def build_signed_request(action,arguments,c,key):
 if action not in ACTIONS or not isinstance(arguments,dict):raise ValueError("ACTION_NOT_ALLOWED")
 now=datetime.now(timezone.utc);r={"protocol_version":"1.0","request_id":str(uuid.uuid4()),"target_device":c.runner_target_device,"action":action,"arguments":arguments,"issued_at":now.isoformat(),"expires_at":(now+timedelta(seconds=60)).isoformat(),"nonce":secrets.token_urlsafe(24),"key_id":c.runner_key_id};r["signature"]=hmac.new(key,canonical_payload(r),hashlib.sha256).hexdigest();return r
def call_runner(r,c):
 body=json.dumps(r,ensure_ascii=False,separators=(",",":")).encode();q=Request(c.runner_base_url+"/v1/task",body,{"Content-Type":"application/json"},method="POST")
 try:
  with build_opener(ProxyHandler({}),NoRedirect()).open(q,timeout=c.request_timeout_seconds) as x:return x.status,json.loads(x.read().decode())
 except HTTPError as e:
  try:
   body_json=json.loads(e.read().decode())
   return e.code,body_json
  except Exception:
   raw=e.read().decode(errors='replace').strip()
   return e.code,{'error_code':f'http_{e.code}','message':raw[:500] if raw else f'HTTP {e.code}'}
 except (TimeoutError,socket.timeout):raise RuntimeError("RUNNER_TIMEOUT")
 except URLError as e:
  reason=e.reason
  if isinstance(reason,(TimeoutError,socket.timeout)) or getattr(reason,"errno",None) in (110,10060):raise RuntimeError("RUNNER_TIMEOUT")
  raise RuntimeError("RUNNER_OFFLINE")
# --- Job API client ---
# Phase 2B-3B R2: Job API uses same signed envelope family as legacy /v1/task.
# action field = "jobs.submit" | "jobs.status" | "jobs.result" | "jobs.cancel"
# arguments field = Runner R1 ProcessJobSpec (or archive compatibility payload).
JOB_ACTIONS=("submit","status","cancel","result")
def _canonical_job_payload(r):
 return json.dumps({k:v for k,v in r.items() if k!="signature"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def build_signed_job_request(job_action,job_payload,c,key):
 # R2: action="jobs.submit", arguments=job_payload (not job_action+payload)
 if job_action not in JOB_ACTIONS:raise ValueError("INVALID_JOB_ACTION")
 now=datetime.now(timezone.utc)
 r={
  "protocol_version":"1.0",
  "request_id":str(uuid.uuid4()),
  "target_device":c.runner_target_device,
  "action":"jobs."+job_action,   # R2 fix: "jobs.submit" not "submit"
  "arguments":job_payload,         # R2 fix: "arguments" not "payload"
  "issued_at":now.isoformat(),
  "expires_at":(now+timedelta(seconds=60)).isoformat(),
  "nonce":secrets.token_urlsafe(24),
  "key_id":c.runner_key_id
 }
 r["signature"]=hmac.new(key,_canonical_job_payload(r),hashlib.sha256).hexdigest();return r
def call_runner_job(r,c):
 # R2: URL uses action sans "jobs." prefix; action field in body = full "jobs.*" name
 body=json.dumps(r,ensure_ascii=False,separators=(",",":")).encode()
 job_url_action=r["action"].replace("jobs.","")  # "jobs.submit" -> "submit"
 q=Request(c.runner_base_url+"/v1/jobs/"+job_url_action,body,{"Content-Type":"application/json"},method="POST")
 try:
  with build_opener(ProxyHandler({}),NoRedirect()).open(q,timeout=c.request_timeout_seconds) as x:return x.status,json.loads(x.read().decode())
 except HTTPError as e:
  try:
   body_json=json.loads(e.read().decode())
   return e.code,body_json
  except Exception:
   raw=e.read().decode(errors='replace').strip()
   return e.code,{'error_code':f'http_{e.code}','message':raw[:500] if raw else f'HTTP {e.code}'}
 except (TimeoutError,socket.timeout):raise RuntimeError("RUNNER_TIMEOUT")
 except URLError as e:
  reason=e.reason
  if isinstance(reason,(TimeoutError,socket.timeout)) or getattr(reason,"errno",None) in (110,10060):raise RuntimeError("RUNNER_TIMEOUT")
  raise RuntimeError("RUNNER_OFFLINE")
def submit_job(job_payload,c,key):
 r=build_signed_job_request("submit",job_payload,c,key);return call_runner_job(r,c)
def job_status(job_id,c,key):
 r=build_signed_job_request("status",{"job_id":job_id},c,key);return call_runner_job(r,c)
def cancel_job(job_id,c,key):
 r=build_signed_job_request("cancel",{"job_id":job_id},c,key);return call_runner_job(r,c)
def job_result(job_id,c,key):
 r=build_signed_job_request("result",{"job_id":job_id},c,key);return call_runner_job(r,c)

# --- Authorization API (Phase 2B-4E2) ---
# Stateless passthrough to Runner. No local state, no auto-approve.
# Follows same HTTP-path-per-endpoint pattern as Jobs API.
# Runner 4E1 contract:
#   POST /v1/authorizations/request  (body: action="authorizations.request", arguments={task, real_workspace})
#   POST /v1/authorizations/approve  (body: action="authorizations.approve", arguments={authorization_request_id})

AUTH_ACTIONS = ("request", "approve")

def _canonical_auth_payload(r):
 return json.dumps({k:v for k,v in r.items() if k!="signature"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()

def build_signed_auth_request(auth_action, auth_payload, c, key):
 if auth_action not in AUTH_ACTIONS:
  raise ValueError("INVALID_AUTH_ACTION")
 now = datetime.now(timezone.utc)
 r = {
  "protocol_version": "1.0",
  "request_id": str(uuid.uuid4()),
  "target_device": c.runner_target_device,
  "action": "authorizations." + auth_action,
  "arguments": auth_payload,
  "issued_at": now.isoformat(),
  "expires_at": (now + timedelta(seconds=60)).isoformat(),
  "nonce": secrets.token_urlsafe(24),
  "key_id": c.runner_key_id,
 }
 r["signature"] = hmac.new(key, _canonical_auth_payload(r), hashlib.sha256).hexdigest()
 return r

def call_runner_auth(r, c):
 body = json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode()
 auth_url_action = r["action"].replace("authorizations.", "")  # "authorizations.request" -> "request"
 q = Request(c.runner_base_url + "/v1/authorizations/" + auth_url_action, body, {"Content-Type": "application/json"}, method="POST")
 try:
  with build_opener(ProxyHandler({}), NoRedirect()).open(q, timeout=c.request_timeout_seconds) as x:
   return x.status, json.loads(x.read().decode())
 except HTTPError as e:
  try:
   return e.code, json.loads(e.read().decode())
  except Exception:
   return e.code, {}
 except (TimeoutError, socket.timeout):
  raise RuntimeError("RUNNER_TIMEOUT")
 except URLError as e:
  reason = e.reason
  if isinstance(reason, (TimeoutError, socket.timeout)) or getattr(reason, "errno", None) in (110, 10060):
   raise RuntimeError("RUNNER_TIMEOUT")
  raise RuntimeError("RUNNER_OFFLINE")

def authorization_request(task, real_workspace, c, key):
 r = build_signed_auth_request("request", {"task": task, "real_workspace": real_workspace}, c, key)
 return call_runner_auth(r, c)

def authorization_approve(authorization_request_id, c, key):
 r = build_signed_auth_request("approve", {"authorization_request_id": authorization_request_id}, c, key)
 return call_runner_auth(r, c)

# --- Worker Control API (Phase 2B-5B) ---
# Stateless passthrough to Runner. Runner owns all paused-state.
# Runner contract:
#   POST /v1/workers/status   (body: action="workers.status",   arguments={})
#   POST /v1/workers/pause    (body: action="workers.pause",    arguments={})
#   POST /v1/workers/resume   (body: action="workers.resume",   arguments={})

WORKER_CONTROL_ACTIONS = ("status", "pause", "resume")

def _canonical_worker_payload(r):
 return json.dumps({k:v for k,v in r.items() if k!="signature"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()

def build_signed_worker_control_request(control_action, c, key):
 if control_action not in WORKER_CONTROL_ACTIONS:
  raise ValueError("INVALID_WORKER_CONTROL_ACTION")
 now = datetime.now(timezone.utc)
 r = {
  "protocol_version": "1.0",
  "request_id": str(uuid.uuid4()),
  "target_device": c.runner_target_device,
  "action": "workers." + control_action,
  "arguments": {},
  "issued_at": now.isoformat(),
  "expires_at": (now + timedelta(seconds=60)).isoformat(),
  "nonce": secrets.token_urlsafe(24),
  "key_id": c.runner_key_id,
 }
 r["signature"] = hmac.new(key, _canonical_worker_payload(r), hashlib.sha256).hexdigest()
 return r

def call_runner_worker_control(r, c):
 body = json.dumps(r, ensure_ascii=False, separators=(",", ":")).encode()
 q = Request(c.runner_base_url + "/v1/workers/" + r["action"].replace("workers.", ""), body, {"Content-Type": "application/json"}, method="POST")
 try:
  with build_opener(ProxyHandler({}), NoRedirect()).open(q, timeout=c.request_timeout_seconds) as x:
   return x.status, json.loads(x.read().decode())
 except HTTPError as e:
  try:
   return e.code, json.loads(e.read().decode())
  except Exception:
   return e.code, {}
 except (TimeoutError, socket.timeout):
  raise RuntimeError("RUNNER_TIMEOUT")
 except URLError as e:
  reason = e.reason
  if isinstance(reason, (TimeoutError, socket.timeout)) or getattr(reason, "errno", None) in (110, 10060):
   raise RuntimeError("RUNNER_TIMEOUT")
  raise RuntimeError("RUNNER_OFFLINE")

def worker_control_status(c, key):
 r = build_signed_worker_control_request("status", c, key)
 return call_runner_worker_control(r, c)

def worker_pause(c, key):
 r = build_signed_worker_control_request("pause", c, key)
 return call_runner_worker_control(r, c)

def worker_resume(c, key):
 r = build_signed_worker_control_request("resume", c, key)
 return call_runner_worker_control(r, c)
