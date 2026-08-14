from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = frozenset({"success", "rejected", "failed"})


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    action: str
    arguments: dict
    requested_by: str
    confirmation_id: str | None = None


@dataclass(frozen=True)
class ActionResult:
    request_id: str
    action: str
    status: str
    output: dict
    error_code: str | None
    error_message: str | None
    started_at: str
    finished_at: str

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUSES:
            raise ValueError("invalid action result status")


JOB_STATUSES = frozenset({
    "queued", "running", "succeeded", "failed", "cancelled", "timed_out", "interrupted_by_restart",
})
JOB_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "timed_out", "interrupted_by_restart"})


@dataclass(frozen=True)
class ProcessJobSpec:
    """Canonical structured Direct Process job; executable is a catalog ID, never a path."""

    type: str
    executable: str
    arguments: tuple[str, ...]
    cwd: Path
    timeout: int
    write_scope: str
    network_policy: str


@dataclass(frozen=True)
class JobResult:
    status: str
    summary: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    error_code: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    status: str
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    job_type: str
    backend: str
    error_code: str | None = None
    error_summary: str | None = None
    result: JobResult | None = None
    restart_classification: str | None = None
