"""Internal, Runner-owned lifecycle supervision for approved process specs."""
from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from .authority import ApprovedProcessSpec, ExecutablePolicy, ProcessRequest, PRODUCTION_EXECUTABLE_CATALOG, approve_process_request
from .config import RunnerConfig
from .jobs import JobStateError, JobStore
from .models import JobRecord, JobResult, ProcessJobSpec
from .programs import PROGRAM_STDERR_MAX_BYTES, PROGRAM_STDOUT_MAX_BYTES, _CapturedOutput, _capture_stream, _minimal_environment


class ProcessSupervisorError(ValueError):
    pass


@dataclass
class _ActiveProcess:
    process: subprocess.Popen[bytes]
    timeout_seconds: int
    completion_hook: Callable[[str, JobResult], JobResult] | None = None
    stdout: _CapturedOutput = field(default_factory=_CapturedOutput)
    stderr: _CapturedOutput = field(default_factory=_CapturedOutput)
    terminal_status: str | None = None
    capture_threads: tuple[threading.Thread, threading.Thread] | None = None


class ProcessSupervisor:
    """Does not persist PIDs and never accepts a raw command or shell form."""

    def __init__(
        self, store: JobStore, config: RunnerConfig, *,
        catalog: Mapping[str, ExecutablePolicy] = PRODUCTION_EXECUTABLE_CATALOG,
        environment: Mapping[str, str] | None = None,
    ):
        self._store = store
        self._config = config
        self._catalog = catalog
        if environment is not None and any(
            not isinstance(key, str) or not isinstance(value, str) or "\x00" in key or "\x00" in value
            for key, value in environment.items()
        ):
            raise ProcessSupervisorError("process environment is invalid")
        self._environment = None if environment is None else dict(environment)
        self._lock = threading.RLock()
        self._active: dict[str, _ActiveProcess] = {}

    def submit(self, request: ProcessJobSpec, *, job_type: str = "process") -> JobRecord:
        spec = approve_process_request(request, self._catalog, self._config)
        job = self._store.create(job_type, spec.executable_id)
        self._start_approved(job.job_id, spec, None)
        return job

    def start(
        self, job_id: str, request: ProcessJobSpec | ProcessRequest,
        completion_hook: Callable[[str, JobResult], JobResult] | None = None,
    ) -> ApprovedProcessSpec:
        spec = approve_process_request(request, self._catalog, self._config)
        self._start_approved(job_id, spec, completion_hook)
        return spec

    def _start_approved(
        self, job_id: str, spec: ApprovedProcessSpec,
        completion_hook: Callable[[str, JobResult], JobResult] | None,
    ) -> None:
        if self._store.get(job_id) is None:
            raise ProcessSupervisorError("job was not found")
        try:
            self._store.transition(job_id, "running")
        except JobStateError as error:
            raise ProcessSupervisorError("job is not queued") from error
        try:
            process = subprocess.Popen(
                [str(spec.executable_path), *spec.argv], cwd=str(spec.cwd),
                env=_minimal_environment() if self._environment is None else self._environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            )
        except OSError:
            result = self._apply_completion_hook(
                job_id, JobResult("failed", "process could not start", error_code="PROCESS_START_FAILED"), completion_hook,
            )
            self._complete(job_id, result.status, result)
            return
        active = _ActiveProcess(process, spec.timeout_seconds, completion_hook)
        with self._lock:
            self._active[job_id] = active
        stdout_thread = threading.Thread(target=_capture_stream, args=(process.stdout, PROGRAM_STDOUT_MAX_BYTES, active.stdout), daemon=True)
        stderr_thread = threading.Thread(target=_capture_stream, args=(process.stderr, PROGRAM_STDERR_MAX_BYTES, active.stderr), daemon=True)
        active.capture_threads = (stdout_thread, stderr_thread)
        stdout_thread.start(); stderr_thread.start()
        threading.Thread(target=self._wait_for_completion, args=(job_id, active), daemon=True).start()

    def cancel(self, job_id: str) -> None:
        record = self._store.get(job_id)
        if record is None:
            raise ProcessSupervisorError("job was not found")
        if record.status == "queued":
            self._complete(job_id, "cancelled", JobResult("cancelled", "job cancelled", error_code="CANCELLED"))
            return
        with self._lock:
            active = self._active.get(job_id)
            if active is None or active.process.poll() is not None:
                return
            active.terminal_status = "cancelled"
            self._terminate_tree(active.process)

    def active_job_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._active)

    def _wait_for_completion(self, job_id: str, active: _ActiveProcess) -> None:
        try:
            active.process.wait(timeout=active.timeout_seconds)
        except subprocess.TimeoutExpired:
            with self._lock:
                if active.process.poll() is None and active.terminal_status is None:
                    active.terminal_status = "timed_out"
                    self._terminate_tree(active.process)
            active.process.wait()
        status = active.terminal_status
        if status is None:
            status = "succeeded" if active.process.returncode == 0 else "failed"
        self._close_streams(active)
        summary = "process completed" if status == "succeeded" else f"process {status}"
        error_code = None if status == "succeeded" else status.upper()
        result = JobResult(
            status, summary, bytes(active.stdout.data).decode("utf-8", errors="replace"),
            bytes(active.stderr.data).decode("utf-8", errors="replace"), active.process.returncode,
            error_code, {"stdout_truncated": active.stdout.truncated, "stderr_truncated": active.stderr.truncated},
        )
        result = self._apply_completion_hook(job_id, result, active.completion_hook)
        self._complete(job_id, result.status, result)
        with self._lock:
            self._active.pop(job_id, None)

    @staticmethod
    def _close_streams(active: _ActiveProcess) -> None:
        if active.capture_threads is not None:
            for thread in active.capture_threads:
                thread.join(timeout=2)
        for stream in (active.process.stdout, active.process.stderr):
            if stream is not None:
                stream.close()

    def _complete(self, job_id: str, status: str, result: JobResult) -> None:
        try:
            self._store.transition(job_id, status, error_code=result.error_code, error_summary=result.summary)
            self._store.set_result(job_id, result)
        except JobStateError:
            return

    @staticmethod
    def _apply_completion_hook(
        job_id: str, result: JobResult, completion_hook: Callable[[str, JobResult], JobResult] | None,
    ) -> JobResult:
        if completion_hook is None:
            return result
        try:
            completed = completion_hook(job_id, result)
        except Exception:
            if result.status != "succeeded":
                return result
            return JobResult("failed", "process completion hook failed", error_code="POST_PROCESS_FAILED")
        if not isinstance(completed, JobResult):
            if result.status != "succeeded":
                return result
            return JobResult("failed", "process completion hook failed", error_code="POST_PROCESS_FAILED")
        if result.status == "succeeded" and completed.status not in {"succeeded", "failed"}:
            return JobResult("failed", "process completion hook failed", error_code="POST_PROCESS_FAILED")
        if result.status != "succeeded" and completed.status != result.status:
            return JobResult("failed", "process completion hook failed", error_code="POST_PROCESS_FAILED")
        return completed

    @staticmethod
    def _terminate_tree(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        taskkill = Path(r"C:\Windows\System32\taskkill.exe")
        try:
            subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False, check=False, timeout=10)
        except (OSError, subprocess.SubprocessError):
            try:
                process.kill()
            except OSError:
                pass
