from __future__ import annotations
import ipaddress,json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
HOME=Path.home()/".config"/"jarvis-bridge"; NET=ipaddress.ip_network("100.64.0.0/10")
ACTIONS=("system.ping","system.info","system.status","files.list_directory","files.search","program.list","program.run")
@dataclass(frozen=True)
class BridgeConfig:
 listen_host:str="127.0.0.1"; listen_port:int=27901; runner_base_url:str="http://100.64.0.10:27891"; runner_key_path:Path=HOME/"runner_auth.key"; bridge_token_path:Path=HOME/"bridge_local.token"; runner_key_id:str="runner-local-v1"; runner_target_device:str="windows-runner"; request_timeout_seconds:int=8; maximum_request_body_bytes:int=65536
def secret_path(value,name):
 path=Path(value).expanduser().resolve(False)
 try:path.relative_to(HOME.resolve(False))
 except ValueError as e:raise ValueError(name) from e
 return path
def validate_config(c):
 if c.listen_host!="127.0.0.1" or c.listen_port!=27901:raise ValueError("loopback only")
 u=urlsplit(c.runner_base_url)
 if u.scheme!="http" or u.username or u.password or u.query or u.fragment or u.path not in ("", "/") or u.port!=27891:raise ValueError("runner url")
 try:a=ipaddress.ip_address(u.hostname or "")
 except ValueError as e:raise ValueError("runner url") from e
 if a.version!=4 or a not in NET:raise ValueError("runner url")
 secret_path(c.runner_key_path,"key");secret_path(c.bridge_token_path,"token")
 if c.runner_key_id!="runner-local-v1" or c.runner_target_device!="windows-runner" or not 1<=c.request_timeout_seconds<=30 or not 1<=c.maximum_request_body_bytes<=65536:raise ValueError("config")
def load_config(root=None):
 v={};p=(root or Path.cwd())/"config"/"bridge.json"
 if p.is_file():v=json.loads(p.read_text("utf-8"))
 c=BridgeConfig(**{**BridgeConfig().__dict__,**v,"runner_key_path":secret_path(v.get("runner_key_path",HOME/"runner_auth.key"),"key"),"bridge_token_path":secret_path(v.get("bridge_token_path",HOME/"bridge_local.token"),"token")});validate_config(c);return c
