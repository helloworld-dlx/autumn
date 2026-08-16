"""In-memory, task-scoped authorization for future Agent L3 publish.

V0.2 does not prove human presence cryptographically. Approval authenticity
depends on the trusted Autumn/OpenClaw control plane that calls this primitive.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Callable

from .authority import AuthorityLevel
from .config import RunnerConfig
from .errors import RunnerError
from .security import validate_read_directory_path


AUTHORIZATION_TTL = timedelta(minutes=10)
AGENT_L3_PUBLISH_EFFECTS = ("CREATE", "MODIFY")
_ADAPTER_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class PendingAuthorization:
    authorization_request_id: str
    subject: str
    adapter: str
    real_workspace: Path
    task_summary: str
    allowed_publish_effects: tuple[str, ...]
    network_policy: str
    authority_level: AuthorityLevel
    created_at: datetime
    expires_at: datetime
    status: str
    approved_at: datetime | None = None
    consumed_at: datetime | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskAuthorizationStore:
    """Runner-owned one-approval, one-consumption L3 authorization memory."""

    def __init__(self, config: RunnerConfig, *, clock: Callable[[], datetime] = _utc_now):
        self._config = config
        self._clock = clock
        self._lock = RLock()
        self._requests: dict[str, PendingAuthorization] = {}

    def create_request(
        self, *, subject: object, adapter: object, real_workspace: object,
        task_summary: object, network_policy: object = "none",
    ) -> PendingAuthorization:
        authenticated_subject = _normalized_subject(subject)
        adapter_id = _normalized_adapter(adapter)
        normalized_task = normalize_task_summary(task_summary, self._config.maximum_argument_string_length)
        if network_policy != "none":
            raise RunnerError("L4_NOT_AUTHORIZED", "task-scoped L3 authorization requires network_policy none")
        if not isinstance(real_workspace, (str, Path)):
            raise RunnerError("AUTHORIZATION_REQUEST_INVALID", "real workspace is invalid")
        workspace = validate_read_directory_path(str(real_workspace), self._config)
        now = self._now()
        with self._lock:
            request_id = str(uuid.uuid4())
            while request_id in self._requests:
                request_id = str(uuid.uuid4())
            request = PendingAuthorization(
                request_id, authenticated_subject, adapter_id, workspace, normalized_task,
                AGENT_L3_PUBLISH_EFFECTS, "none", AuthorityLevel.L3_WORKSPACE_WRITE,
                now, now + AUTHORIZATION_TTL, "pending",
            )
            self._requests[request_id] = request
            return request

    def list_pending(self) -> tuple[PendingAuthorization, ...]:
        """Return only currently fresh pending requests for read-only status surfaces."""
        now = self._now()
        with self._lock:
            return tuple(
                request for request in self._requests.values()
                if request.status == "pending" and now < request.expires_at
            )

    def approve(self, authorization_request_id: object, *, subject: object) -> PendingAuthorization:
        authenticated_subject = _normalized_subject(subject)
        with self._lock:
            request = self._require(authorization_request_id)
            self._require_subject(request, authenticated_subject)
            now = self._now()
            self._require_fresh(request, now)
            if request.status == "approved":
                raise RunnerError("AUTHORIZATION_ALREADY_APPROVED", "authorization request was already approved")
            if request.status == "consumed":
                raise RunnerError("AUTHORIZATION_CONSUMED", "authorization request was already consumed")
            approved = replace(request, status="approved", approved_at=now)
            self._requests[request.authorization_request_id] = approved
            return approved

    def consume(self, authorization_request_id: object, *, subject: object) -> PendingAuthorization:
        authenticated_subject = _normalized_subject(subject)
        with self._lock:
            request = self._require(authorization_request_id)
            self._require_subject(request, authenticated_subject)
            if request.status == "consumed":
                raise RunnerError("AUTHORIZATION_CONSUMED", "authorization request was already consumed")
            now = self._now()
            self._require_fresh(request, now)
            if request.status != "approved":
                raise RunnerError("AUTHORIZATION_NOT_APPROVED", "authorization request is not approved")
            consumed = replace(request, status="consumed", consumed_at=now)
            self._requests[request.authorization_request_id] = consumed
            return consumed

    def _require(self, authorization_request_id: object) -> PendingAuthorization:
        if not isinstance(authorization_request_id, str):
            raise RunnerError("AUTHORIZATION_NOT_FOUND", "authorization request was not found")
        request = self._requests.get(authorization_request_id)
        if request is None:
            raise RunnerError("AUTHORIZATION_NOT_FOUND", "authorization request was not found")
        return request

    @staticmethod
    def _require_subject(request: PendingAuthorization, subject: str) -> None:
        if request.subject != subject:
            raise RunnerError("AUTHORIZATION_SUBJECT_MISMATCH", "authorization subject does not match")

    @staticmethod
    def _require_fresh(request: PendingAuthorization, now: datetime) -> None:
        if now >= request.expires_at:
            raise RunnerError("AUTHORIZATION_EXPIRED", "authorization request expired")

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("authorization clock must return a timezone-aware datetime")
        return now.astimezone(timezone.utc)


def _normalized_subject(value: object) -> str:
    if not isinstance(value, str):
        raise RunnerError("AUTHORIZATION_REQUEST_INVALID", "authorization subject is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > 256 or any(ord(character) < 32 for character in normalized):
        raise RunnerError("AUTHORIZATION_REQUEST_INVALID", "authorization subject is invalid")
    return normalized


def _normalized_adapter(value: object) -> str:
    if not isinstance(value, str) or not _ADAPTER_ID.fullmatch(value):
        raise RunnerError("AUTHORIZATION_REQUEST_INVALID", "adapter identity is invalid")
    return value


def normalize_task_summary(value: object, maximum_length: int) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise RunnerError("AUTHORIZATION_REQUEST_INVALID", "task summary is invalid")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum_length:
        raise RunnerError("AUTHORIZATION_REQUEST_INVALID", "task summary is invalid")
    return normalized
