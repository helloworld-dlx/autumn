"""In-memory Autumn Node Protocol Lite V1 registry."""
from datetime import datetime, timedelta, timezone

PROTOCOL_VERSION = "1"
PI5_CORE = {
    "protocol_version": PROTOCOL_VERSION,
    "node_id": "pi5-core",
    "node_type": "core",
    "node_version": "v0.2-frozen",
    "capabilities": ["agent.main", "gateway", "bridge.forward", "home.read", "home.control"],
    "metadata": {},
}
WINDOWS_MAIN = {
    "protocol_version": PROTOCOL_VERSION,
    "node_id": "windows-main",
    "node_type": "windows",
    "node_version": "runner-v1",
    "capabilities": ["system.status", "file.search", "file.return", "job.submit", "job.status", "job.cancel", "codex.submit"],
    "metadata": {},
}
XIAOMI15 = {
    "protocol_version": PROTOCOL_VERSION,
    "node_id": "xiaomi15",
    "node_type": "phone",
    "node_version": "companion-pwa-v19",
    "capabilities": ["voice.listen", "voice.speak", "camera.capture", "open_url", "clipboard.set"],
    "metadata": {},
}
PI_HEALTH_TTL = timedelta(seconds=90)  # retained for protocol compatibility; core presence is self-evident when served
WINDOWS_HEALTH_TTL = timedelta(seconds=180)
PHONE_RECENT_TTL = timedelta(minutes=10)
MAX_PUBLIC_NODES = 16
_FIELDS = frozenset(("protocol_version", "node_id", "node_type", "node_version", "last_seen", "capabilities", "metadata"))
_NODE_TYPES = frozenset(("core", "windows", "phone"))


def _now():
 return datetime.now(timezone.utc)


def _timestamp(value):
 if value is None:return None
 if not isinstance(value,str):raise ValueError("invalid last_seen")
 try:parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
 except ValueError as error:raise ValueError("invalid last_seen") from error
 if parsed.tzinfo is None:raise ValueError("invalid last_seen")
 return parsed.astimezone(timezone.utc)


def _validate(descriptor):
 if not isinstance(descriptor,dict) or set(descriptor)!=_FIELDS:raise ValueError("invalid node descriptor")
 if descriptor["protocol_version"]!=PROTOCOL_VERSION:raise ValueError("invalid node descriptor")
 if not isinstance(descriptor["node_id"],str) or not descriptor["node_id"]:raise ValueError("invalid node descriptor")
 if descriptor["node_type"] not in _NODE_TYPES:raise ValueError("invalid node descriptor")
 if not isinstance(descriptor["node_version"],str) or not descriptor["node_version"]:raise ValueError("invalid node descriptor")
 if not isinstance(descriptor["capabilities"],list) or not all(isinstance(item,str) and item and item==item.lower() for item in descriptor["capabilities"]):raise ValueError("invalid node descriptor")
 if not isinstance(descriptor["metadata"],dict) or descriptor["metadata"]:raise ValueError("invalid node descriptor")
 return _timestamp(descriptor["last_seen"])


class NodeRegistry:
 def __init__(self,clock=_now):self._clock=clock;self._nodes={}
 def upsert(self,descriptor):
  seen=_validate(descriptor) or self._clock()
  self._nodes[descriptor["node_id"]]={key:value for key,value in descriptor.items() if key!="last_seen"};self._nodes[descriptor["node_id"]]["last_seen"]=seen
  return self.get(descriptor["node_id"])
 def touch(self,node_id):
  if node_id not in self._nodes:return None
  self._nodes[node_id]["last_seen"]=self._clock();return self.get(node_id)
 def get(self,node_id):
  node=self._nodes.get(node_id)
  return None if node is None else self._public(node)
 def list(self):return [self._public(node) for _,node in sorted(self._nodes.items())[:MAX_PUBLIC_NODES]]
 def _public(self,node):
  last_seen=node["last_seen"]
  return {"protocol_version":node["protocol_version"],"node_id":node["node_id"],"node_type":node["node_type"],"node_version":node["node_version"],"online":self.derive_presence(node["node_type"],last_seen),"last_seen":last_seen.isoformat().replace("+00:00","Z"),"capabilities":list(node["capabilities"]),"metadata":dict(node["metadata"])}
 def derive_presence(self,node_type,last_seen):
  if last_seen is None:return "UNKNOWN"
  # The registry itself is hosted by pi5-core. If callers can read this
  # registry, the core node is necessarily reachable; do not let an unrelated
  # probe-loop timestamp make the Pi report itself OFFLINE.
  if node_type=="core":return "ONLINE"
  age=self._clock()-last_seen
  if node_type=="phone":return "RECENT" if age<=PHONE_RECENT_TTL else "UNKNOWN"
  return "ONLINE" if age<=WINDOWS_HEALTH_TTL else "OFFLINE"
