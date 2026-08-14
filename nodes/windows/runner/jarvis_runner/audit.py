from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .config import AUDIT_BACKUP_COUNT_HARD_LIMIT, AUDIT_MAX_BYTES_HARD_LIMIT, RunnerConfig
from .models import ActionRequest, ActionResult
from .security import redact_for_audit, validate_controlled_write_path


_AUDIT_LOCK = Lock()
_CANONICAL_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


def _rotate_audit_files(audit_path: Path, backup_count: int) -> None:
    oldest_backup = audit_path.with_name(f"{audit_path.name}.{backup_count}")
    if oldest_backup.exists():
        oldest_backup.unlink()
    for index in range(backup_count - 1, 0, -1):
        source = audit_path.with_name(f"{audit_path.name}.{index}")
        target = audit_path.with_name(f"{audit_path.name}.{index + 1}")
        if source.exists():
            source.replace(target)
    if audit_path.exists():
        audit_path.replace(audit_path.with_name(f"{audit_path.name}.1"))


def append_audit_record(request: ActionRequest, result: ActionResult, config: RunnerConfig) -> None:
    record = {
        "request_id": request.request_id,
        "action": request.action,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "arguments": "[SIGNED_REQUEST_REDACTED]" if request.requested_by == "signed-protocol" else redact_for_audit(request.arguments),
    }
    record_bytes = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if not isinstance(config.audit_max_bytes, int) or isinstance(config.audit_max_bytes, bool) or not 1 <= config.audit_max_bytes <= AUDIT_MAX_BYTES_HARD_LIMIT:
        raise ValueError("audit_max_bytes must be a positive integer within its code hard limit")
    if not isinstance(config.audit_backup_count, int) or isinstance(config.audit_backup_count, bool) or not 1 <= config.audit_backup_count <= AUDIT_BACKUP_COUNT_HARD_LIMIT:
        raise ValueError("audit_backup_count must be between 1 and its code hard limit")
    if len(record_bytes) > config.audit_max_bytes:
        raise ValueError("audit record exceeds audit_max_bytes")

    with _AUDIT_LOCK:
        audit_path = validate_controlled_write_path(config.audit_log, config)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        current_size = audit_path.stat().st_size if audit_path.exists() else 0
        if current_size + len(record_bytes) > config.audit_max_bytes:
            _rotate_audit_files(audit_path, config.audit_backup_count)
        with audit_path.open("ab") as handle:
            handle.write(record_bytes)


def append_file_export_audit(
    request_id: str,
    status: str,
    file_size: int | None,
    duration_ms: int,
    error_code: str | None,
    config: RunnerConfig,
) -> None:
    """Write file-export metadata without ever accepting file content."""
    record = {
        "request_id": request_id,
        "action": "file.export",
        "status": status,
        "file_size_bytes": file_size,
        "duration_ms": duration_ms,
        "error_code": error_code,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    record_bytes = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if not isinstance(config.audit_max_bytes, int) or isinstance(config.audit_max_bytes, bool) or not 1 <= config.audit_max_bytes <= AUDIT_MAX_BYTES_HARD_LIMIT:
        raise ValueError("audit_max_bytes must be a positive integer within its code hard limit")
    if not isinstance(config.audit_backup_count, int) or isinstance(config.audit_backup_count, bool) or not 1 <= config.audit_backup_count <= AUDIT_BACKUP_COUNT_HARD_LIMIT:
        raise ValueError("audit_backup_count must be between 1 and its code hard limit")
    if len(record_bytes) > config.audit_max_bytes:
        raise ValueError("audit record exceeds audit_max_bytes")

    with _AUDIT_LOCK:
        audit_path = validate_controlled_write_path(config.audit_log, config)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        current_size = audit_path.stat().st_size if audit_path.exists() else 0
        if current_size + len(record_bytes) > config.audit_max_bytes:
            _rotate_audit_files(audit_path, config.audit_backup_count)
        with audit_path.open("ab") as handle:
            handle.write(record_bytes)


def append_job_audit_event(job_id: str, event: str, status: str, error_code: str | None, config: RunnerConfig) -> None:
    """Append bounded Job lifecycle metadata; never include result streams or inputs."""
    if event not in {
        "job_submitted", "job_started", "job_succeeded", "job_failed", "job_cancelled",
        "job_timed_out", "job_interrupted_by_restart",
    }:
        raise ValueError("invalid job audit event")
    record = {
        "job_id": job_id,
        "action": event,
        "status": status,
        "error_code": error_code,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    record_bytes = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(record_bytes) > config.audit_max_bytes:
        raise ValueError("audit record exceeds audit_max_bytes")
    with _AUDIT_LOCK:
        audit_path = validate_controlled_write_path(config.audit_log, config)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        current_size = audit_path.stat().st_size if audit_path.exists() else 0
        if current_size + len(record_bytes) > config.audit_max_bytes:
            _rotate_audit_files(audit_path, config.audit_backup_count)
        with audit_path.open("ab") as handle:
            handle.write(record_bytes)


def append_codex_start_rejected_audit(
    job_id: str, underlying_exception: Exception, config: RunnerConfig, *,
    argv_count: int | None = None, max_arg_length: int | None = None,
    allowed_max_arg_length: int | None = None, timeout: int | None = None,
) -> None:
    """Record bounded Codex-start diagnostics without recording request inputs."""
    underlying_error_code = getattr(underlying_exception, "code", None)
    if not isinstance(underlying_error_code, str) or not _CANONICAL_ERROR_CODE.fullmatch(underlying_error_code):
        underlying_error_code = None
    record = {
        "job_id": job_id,
        "action": "codex_start_rejected",
        "status": "cancelled",
        "error_code": "CODEX_START_REJECTED",
        "underlying_exception_class": type(underlying_exception).__name__,
        "underlying_error_code": underlying_error_code,
        "safe_message": "Codex worker could not be started",
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    if underlying_error_code == "PROCESS_SPEC_INVALID":
        record.update({
            "argv_count": argv_count,
            "max_arg_length": max_arg_length,
            "allowed_max_arg_length": allowed_max_arg_length,
            "timeout": timeout,
            "first_failing_rule": (
                "ARGV_ITEM_TOO_LONG"
                if isinstance(max_arg_length, int)
                and isinstance(allowed_max_arg_length, int)
                and max_arg_length > allowed_max_arg_length
                else None
            ),
        })
    record_bytes = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(record_bytes) > config.audit_max_bytes:
        raise ValueError("audit record exceeds audit_max_bytes")
    with _AUDIT_LOCK:
        audit_path = validate_controlled_write_path(config.audit_log, config)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        current_size = audit_path.stat().st_size if audit_path.exists() else 0
        if current_size + len(record_bytes) > config.audit_max_bytes:
            _rotate_audit_files(audit_path, config.audit_backup_count)
        with audit_path.open("ab") as handle:
            handle.write(record_bytes)


def append_runner_started_audit(
    pid: int, executable: str, package_root: Path, authority_file: Path,
    codex_worker_file: Path, codex_argv_limit: int, codex_wrapper_length: int,
    config: RunnerConfig,
) -> None:
    """Persist only safe Runner runtime identity and fixed Codex policy values."""
    record = {
        "action": "runner_started",
        "pid": pid,
        "sys_executable": executable,
        "package_root": str(package_root),
        "authority_file": str(authority_file),
        "codex_worker_file": str(codex_worker_file),
        "codex_argv_single_item_limit": codex_argv_limit,
        "codex_policy_wrapper_length": codex_wrapper_length,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    record_bytes = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(record_bytes) > config.audit_max_bytes:
        raise ValueError("audit record exceeds audit_max_bytes")
    with _AUDIT_LOCK:
        audit_path = validate_controlled_write_path(config.audit_log, config)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        current_size = audit_path.stat().st_size if audit_path.exists() else 0
        if current_size + len(record_bytes) > config.audit_max_bytes:
            _rotate_audit_files(audit_path, config.audit_backup_count)
        with audit_path.open("ab") as handle:
            handle.write(record_bytes)
