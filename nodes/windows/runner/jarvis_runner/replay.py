from __future__ import annotations

import threading
from datetime import datetime

from .errors import RunnerError


class ReplayCache:
    def __init__(self) -> None:
        self._lock = threading.Lock(); self._requests: dict[str, datetime] = {}; self._nonces: dict[str, datetime] = {}
    def register(self, request_id: str, nonce: str, expires_at: datetime, now: datetime) -> None:
        with self._lock:
            self._requests = {key: value for key, value in self._requests.items() if value > now}
            self._nonces = {key: value for key, value in self._nonces.items() if value > now}
            if request_id in self._requests or nonce in self._nonces:
                raise RunnerError("REQUEST_REPLAYED", "request was already accepted")
            self._requests[request_id] = expires_at; self._nonces[nonce] = expires_at


REPLAY_CACHE = ReplayCache()
