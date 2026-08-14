from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from .errors import RunnerError


REQUIRED_FIELDS = frozenset({"protocol_version", "request_id", "target_device", "action", "arguments", "issued_at", "expires_at", "nonce", "key_id", "signature"})
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")


def canonical_payload(request: dict) -> bytes:
    payload = {key: value for key, value in request.items() if key != "signature"}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise RunnerError("PROTOCOL_INVALID", f"invalid {name}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RunnerError("PROTOCOL_INVALID", f"invalid {name}") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise RunnerError("PROTOCOL_INVALID", f"invalid {name}")
    return parsed


def validate_request(request: object, *, now: datetime | None = None) -> tuple[dict, datetime]:
    if not isinstance(request, dict) or set(request) != REQUIRED_FIELDS:
        raise RunnerError("PROTOCOL_INVALID", "invalid request structure")
    if request["protocol_version"] != "1.0" or request["target_device"] != "windows-runner" or request["key_id"] != "runner-local-v1":
        raise RunnerError("PROTOCOL_INVALID", "invalid request protocol")
    try:
        uuid.UUID(str(request["request_id"]))
    except (ValueError, AttributeError, TypeError) as error:
        raise RunnerError("PROTOCOL_INVALID", "invalid request_id") from error
    if not isinstance(request["action"], str) or not isinstance(request["arguments"], dict):
        raise RunnerError("PROTOCOL_INVALID", "invalid request action")
    if not isinstance(request["nonce"], str) or not _NONCE.fullmatch(request["nonce"]):
        raise RunnerError("PROTOCOL_INVALID", "invalid nonce")
    if not isinstance(request["signature"], str) or not _SIGNATURE.fullmatch(request["signature"]):
        raise RunnerError("AUTH_FAILED", "authentication failed")
    issued, expires = _utc(request["issued_at"], "issued_at"), _utc(request["expires_at"], "expires_at")
    if expires <= issued or expires - issued > timedelta(minutes=5):
        raise RunnerError("PROTOCOL_INVALID", "invalid request lifetime")
    current = now or datetime.now(timezone.utc)
    if issued - current > timedelta(seconds=30):
        raise RunnerError("REQUEST_NOT_YET_VALID", "request is not yet valid")
    if expires <= current:
        raise RunnerError("REQUEST_EXPIRED", "request has expired")
    return request, expires
