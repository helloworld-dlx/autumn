from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Callable

from .config import RunnerConfig
from .models import JOB_STATUSES, JOB_TERMINAL_STATUSES, JobRecord, JobResult
from .programs import PROGRAM_STDERR_MAX_BYTES, PROGRAM_STDOUT_MAX_BYTES
from .security import validate_controlled_write_path, validate_output


_LABEL = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_TRANSITIONS = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "cancelled", "timed_out", "interrupted_by_restart"}),
}
_EVENTS = {
    "queued": "job_submitted", "running": "job_started", "succeeded": "job_succeeded",
    "failed": "job_failed", "cancelled": "job_cancelled", "timed_out": "job_timed_out",
    "interrupted_by_restart": "job_interrupted_by_restart",
}


class JobStateError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise JobStateError("job timestamp must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise JobStateError("invalid persisted job timestamp") from error
    if parsed.tzinfo is None:
        raise JobStateError("persisted job timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _result_dict(result: JobResult) -> dict:
    return asdict(result)


def _record_dict(record: JobRecord) -> dict:
    data = asdict(record)
    return data


def _result_from_dict(value: object) -> JobResult | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise JobStateError("persisted job result is invalid")
    return JobResult(**value)


def _record_from_dict(value: object) -> JobRecord:
    if not isinstance(value, dict):
        raise JobStateError("persisted job record is invalid")
    data = dict(value)
    data["result"] = _result_from_dict(data.get("result"))
    try:
        record = JobRecord(**data)
    except TypeError as error:
        raise JobStateError("persisted job record is invalid") from error
    _validate_record_shape(record)
    return record


def _validate_record_shape(record: JobRecord) -> None:
    if not isinstance(record.job_id, str) or not record.job_id:
        raise JobStateError("job_id is invalid")
    if record.status not in JOB_STATUSES:
        raise JobStateError("job status is invalid")
    if not _LABEL.fullmatch(record.job_type) or not _LABEL.fullmatch(record.backend):
        raise JobStateError("job type or backend is invalid")
    for moment in (record.created_at, record.updated_at):
        _parse_timestamp(moment)
    for moment in (record.started_at, record.finished_at):
        if moment is not None:
            _parse_timestamp(moment)
    if record.status in JOB_TERMINAL_STATUSES and record.finished_at is None:
        raise JobStateError("terminal job must have finished_at")
    if record.status == "running" and record.started_at is None:
        raise JobStateError("running job must have started_at")
    if record.result is not None and record.result.status != record.status:
        raise JobStateError("job result status must match job status")


def _validate_result(result: JobResult, config: RunnerConfig) -> None:
    if result.status not in JOB_TERMINAL_STATUSES:
        raise JobStateError("result status must be terminal")
    if not isinstance(result.stdout, str) or len(result.stdout.encode("utf-8")) > PROGRAM_STDOUT_MAX_BYTES:
        raise JobStateError("stdout exceeds configured byte limit")
    if not isinstance(result.stderr, str) or len(result.stderr.encode("utf-8")) > PROGRAM_STDERR_MAX_BYTES:
        raise JobStateError("stderr exceeds configured byte limit")
    if result.summary is not None and not isinstance(result.summary, str):
        raise JobStateError("result summary is invalid")
    if result.error_code is not None and not isinstance(result.error_code, str):
        raise JobStateError("result error_code is invalid")
    if result.exit_code is not None and (not isinstance(result.exit_code, int) or isinstance(result.exit_code, bool)):
        raise JobStateError("result exit_code is invalid")
    validate_output(_result_dict(result), config)


class JobStore:
    """Runner-owned, lock-protected bounded Job state with atomic local snapshots."""

    def __init__(self, config: RunnerConfig, audit_callback: Callable[[str, str, str, str | None, RunnerConfig], None] | None = None):
        self._config = config
        self._audit_callback = audit_callback
        self._lock = RLock()
        self._records: dict[str, JobRecord] = {}
        self._state_path = validate_controlled_write_path(config.job_state_path, config)

    def create(self, job_type: str, backend: str, *, now: datetime | None = None) -> JobRecord:
        if not _LABEL.fullmatch(job_type) or not _LABEL.fullmatch(backend):
            raise JobStateError("job type and backend must be bounded labels")
        with self._lock:
            moment = now or _now()
            self.prune(now=moment, persist=False)
            if len(self._records) >= self._config.job_max_records:
                raise JobStateError("job store is full")
            job_id = str(uuid.uuid4())
            while job_id in self._records:
                job_id = str(uuid.uuid4())
            stamp = _timestamp(moment)
            record = JobRecord(job_id, "queued", stamp, stamp, None, None, job_type, backend)
            self._records[job_id] = record
            self._persist_locked()
            self._emit(record)
            return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._records.get(job_id)

    def list_records(self) -> tuple[JobRecord, ...]:
        with self._lock:
            return tuple(self._records.values())

    def transition(self, job_id: str, target: str, *, error_code: str | None = None, error_summary: str | None = None, now: datetime | None = None) -> JobRecord:
        if target not in JOB_STATUSES:
            raise JobStateError("target job status is invalid")
        if error_code is not None and not isinstance(error_code, str):
            raise JobStateError("error_code is invalid")
        if error_summary is not None and not isinstance(error_summary, str):
            raise JobStateError("error_summary is invalid")
        if error_code is not None and len(error_code) > 128:
            raise JobStateError("error_code exceeds maximum length")
        if error_summary is not None and len(error_summary) > self._config.maximum_output_string_length:
            raise JobStateError("error_summary exceeds configured length")
        with self._lock:
            record = self._require(job_id)
            if record.status in JOB_TERMINAL_STATUSES:
                raise JobStateError("terminal job cannot transition")
            if target not in _TRANSITIONS.get(record.status, frozenset()):
                raise JobStateError(f"illegal job transition: {record.status} -> {target}")
            moment = now or _now()
            stamp = _timestamp(moment)
            changed = replace(
                record, status=target, updated_at=stamp,
                started_at=stamp if target == "running" else record.started_at,
                finished_at=stamp if target in JOB_TERMINAL_STATUSES else None,
                error_code=error_code, error_summary=error_summary,
            )
            self._records[job_id] = changed
            self._persist_locked()
            self._emit(changed)
            return changed

    def set_result(self, job_id: str, result: JobResult, *, now: datetime | None = None) -> JobRecord:
        _validate_result(result, self._config)
        with self._lock:
            record = self._require(job_id)
            if record.status != result.status:
                raise JobStateError("result status does not match job status")
            if record.status not in JOB_TERMINAL_STATUSES:
                raise JobStateError("result cannot be set on an active job")
            if record.result is not None:
                raise JobStateError("job result is immutable")
            stamp = _timestamp(now or _now())
            changed = replace(record, result=result, updated_at=stamp)
            self._records[job_id] = changed
            self._persist_locked()
            return changed

    def prune(self, *, now: datetime | None = None, persist: bool = True) -> int:
        with self._lock:
            moment = now or _now()
            cutoff = moment - timedelta(seconds=self._config.job_terminal_ttl_seconds)
            expired = [
                job_id for job_id, record in self._records.items()
                if record.status in JOB_TERMINAL_STATUSES and record.finished_at is not None and _parse_timestamp(record.finished_at) <= cutoff
            ]
            for job_id in expired:
                del self._records[job_id]
            if expired and persist:
                self._persist_locked()
            return len(expired)

    def load(self, *, recovery_time: datetime | None = None) -> None:
        with self._lock:
            if not self._state_path.exists():
                return
            try:
                raw = json.loads(self._state_path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("records"), list):
                    raise JobStateError("job state snapshot is invalid")
                records = [_record_from_dict(value) for value in raw["records"]]
            except (OSError, json.JSONDecodeError, JobStateError) as error:
                raise JobStateError("job state snapshot could not be loaded") from error
            if len(records) > self._config.job_max_records or len({record.job_id for record in records}) != len(records):
                raise JobStateError("job state snapshot exceeds store limits")
            self._records = {record.job_id: record for record in records}
            moment = recovery_time or _now()
            stamp = _timestamp(moment)
            for job_id, record in tuple(self._records.items()):
                if record.status not in JOB_TERMINAL_STATUSES:
                    recovered = replace(
                        record, status="interrupted_by_restart", updated_at=stamp, finished_at=stamp,
                        error_code="INTERRUPTED_BY_RESTART", error_summary="job was interrupted by Runner restart",
                        restart_classification="interrupted_by_restart",
                    )
                    self._records[job_id] = recovered
                    self._emit(recovered)
            self.prune(now=moment, persist=False)
            self._persist_locked()

    def _require(self, job_id: str) -> JobRecord:
        record = self._records.get(job_id)
        if record is None:
            raise JobStateError("job was not found")
        return record

    def _emit(self, record: JobRecord) -> None:
        if self._audit_callback is not None:
            self._audit_callback(record.job_id, _EVENTS[record.status], record.status, record.error_code, self._config)

    def _persist_locked(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "records": [_record_dict(record) for record in self._records.values()]}
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        temporary = self._state_path.with_name(f".{self._state_path.name}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._state_path)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise JobStateError("job state snapshot could not be persisted") from error
