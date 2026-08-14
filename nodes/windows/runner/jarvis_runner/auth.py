from __future__ import annotations

import hmac
from pathlib import Path

from .errors import RunnerError
from .config import PRODUCTION_SECRET_ROOT
from .protocol import canonical_payload
from .security import _is_reparse_point


def load_auth_key(path: Path) -> bytes:
    path = Path(path)
    _validate_production_key_components(path)
    if _is_reparse_point(path) or not path.is_file():
        raise RunnerError("AUTH_KEY_UNAVAILABLE", "authentication key unavailable")
    try:
        key = path.read_bytes().rstrip(b"\r\n")
    except OSError as error:
        raise RunnerError("AUTH_KEY_UNAVAILABLE", "authentication key unavailable") from error
    if not 32 <= len(key) <= 128:
        raise RunnerError("AUTH_KEY_UNAVAILABLE", "authentication key unavailable")
    return key


def _validate_production_key_components(path: Path) -> None:
    """Fail closed if a production key path contains a reparse point.

    Directly constructed test configurations may use a temporary key path;
    production configuration is already constrained to this fixed root.
    """
    try:
        relative = path.absolute().relative_to(PRODUCTION_SECRET_ROOT.absolute())
    except ValueError:
        return
    current = PRODUCTION_SECRET_ROOT.absolute()
    for component in relative.parts:
        if _is_reparse_point(current):
            raise RunnerError("AUTH_KEY_UNAVAILABLE", "authentication key unavailable")
        current = current / component
    if _is_reparse_point(current):
        raise RunnerError("AUTH_KEY_UNAVAILABLE", "authentication key unavailable")


def verify_signature(request: dict, key: bytes) -> None:
    expected = hmac.new(key, canonical_payload(request), "sha256").hexdigest()
    if not hmac.compare_digest(expected, request["signature"]):
        raise RunnerError("AUTH_FAILED", "authentication failed")


def sign_request(request: dict, key: bytes) -> str:
    return hmac.new(key, canonical_payload(request), "sha256").hexdigest()
