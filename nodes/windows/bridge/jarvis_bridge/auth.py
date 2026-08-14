import hmac
def load_secret(path):
 try:v=path.read_bytes().rstrip(b"\r\n")
 except OSError:raise ValueError("BRIDGE_KEY_UNAVAILABLE")
 if len(v)<32:raise ValueError("BRIDGE_KEY_UNAVAILABLE")
 return v
def token_matches(value,secret):return isinstance(value,str) and hmac.compare_digest(value.encode(),secret)
