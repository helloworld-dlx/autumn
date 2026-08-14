from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .errors import RunnerError
from .security import _is_reparse_point


PROGRAM_ROOT = Path(r"D:\JarvisScripts")
HELLO_SCRIPT_PATH = PROGRAM_ROOT / "hello_jarvis.py"
HELLO_SCRIPT_SHA256 = "DF6D0E926E8BCD7F42E6126715200244621BD4187C4327ECFECDB27F2229AB56"
PROGRAM_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
PROGRAM_STDOUT_MAX_BYTES = 8192
PROGRAM_STDERR_MAX_BYTES = 8192
PROGRAM_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class ProgramSpec:
    program_id: str
    path: Path
    description: str
    expected_sha256: str
    timeout_seconds: int
    stdout_max_bytes: int
    stderr_max_bytes: int
    read_only: bool = True
    accepts_arguments: bool = False


PROGRAM_REGISTRY: dict[str, ProgramSpec] = {
    "hello_jarvis": ProgramSpec(
        program_id="hello_jarvis",
        path=HELLO_SCRIPT_PATH,
        description="Returns a small JSON greeting and runtime identity.",
        expected_sha256=HELLO_SCRIPT_SHA256,
        timeout_seconds=PROGRAM_TIMEOUT_SECONDS,
        stdout_max_bytes=PROGRAM_STDOUT_MAX_BYTES,
        stderr_max_bytes=PROGRAM_STDERR_MAX_BYTES,
    ),
}

_MINIMAL_ENVIRONMENT_NAMES = ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "PATHEXT")


@dataclass
class _CapturedOutput:
    data: bytearray = field(default_factory=bytearray)
    truncated: bool = False


def program_list(arguments: dict, config: object) -> dict:
    del config
    if arguments != {}:
        raise ValueError("program.list accepts no arguments")
    return {
        "programs": [
            {
                "program_id": spec.program_id,
                "description": spec.description,
                "accepts_arguments": spec.accepts_arguments,
                "read_only": spec.read_only,
                "timeout_seconds": spec.timeout_seconds,
            }
            for spec in PROGRAM_REGISTRY.values()
        ]
    }


def program_run(arguments: dict, config: object) -> dict:
    del config
    if set(arguments) != {"program_id"}:
        raise ValueError("program.run requires exactly program_id")
    program_id = arguments["program_id"]
    if not isinstance(program_id, str) or not PROGRAM_ID_PATTERN.fullmatch(program_id):
        raise ValueError("program_id is invalid")
    spec = PROGRAM_REGISTRY.get(program_id)
    if spec is None:
        raise RunnerError("PROGRAM_NOT_ALLOWED", "program is not registered")
    _validate_program_file(spec)
    return _execute_program(spec)


def _validate_program_file(spec: ProgramSpec) -> None:
    raw_root = str(PROGRAM_ROOT).replace("/", "\\")
    raw_path = str(spec.path).replace("/", "\\")
    if raw_root.startswith(("\\\\", "\\\\?\\", "\\\\.\\")) or raw_path.startswith(("\\\\", "\\\\?\\", "\\\\.\\")):
        raise RunnerError("PROGRAM_PATH_INVALID", "program path is invalid")
    if ":" in raw_root[2:] or ":" in raw_path[2:]:
        raise RunnerError("PROGRAM_PATH_INVALID", "program path is invalid")
    expected_path = PROGRAM_ROOT / "hello_jarvis.py"
    if raw_path.casefold() != str(expected_path).replace("/", "\\").casefold():
        raise RunnerError("PROGRAM_PATH_INVALID", "program path is invalid")
    try:
        spec.path.relative_to(PROGRAM_ROOT)
    except ValueError as error:
        raise RunnerError("PROGRAM_PATH_INVALID", "program path is invalid") from error
    if not PROGRAM_ROOT.exists() or not spec.path.exists():
        raise RunnerError("PROGRAM_FILE_MISSING", "program file is missing")
    if _is_reparse_point(PROGRAM_ROOT) or _is_reparse_point(spec.path):
        raise RunnerError("PROGRAM_PATH_INVALID", "program path is invalid")
    if not spec.path.is_file():
        raise RunnerError("PROGRAM_PATH_INVALID", "program path is invalid")
    try:
        resolved_path = spec.path.resolve(strict=True)
        resolved_path.relative_to(PROGRAM_ROOT.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise RunnerError("PROGRAM_PATH_INVALID", "program path is invalid") from error

    digest = _sha256(spec.path)
    if digest.casefold() != spec.expected_sha256.casefold():
        raise RunnerError("PROGRAM_HASH_MISMATCH", "program integrity check failed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _minimal_environment() -> dict[str, str]:
    environment = {
        name: os.environ[name]
        for name in _MINIMAL_ENVIRONMENT_NAMES
        if name in os.environ
    }
    environment.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
    })
    return environment


def _capture_stream(stream: object, maximum_bytes: int, capture: _CapturedOutput) -> None:
    try:
        while True:
            chunk = stream.read1(4096)  # type: ignore[union-attr]
            if not chunk:
                return
            remaining = maximum_bytes - len(capture.data)
            if remaining > 0:
                capture.data.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    capture.truncated = True
            else:
                capture.truncated = True
    except OSError:
        return


def _execute_program(spec: ProgramSpec) -> dict:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(spec.path)],
            cwd=str(PROGRAM_ROOT),
            env=_minimal_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError as error:
        raise RunnerError("PROGRAM_EXECUTION_FAILED", "program execution failed") from error

    stdout_capture = _CapturedOutput()
    stderr_capture = _CapturedOutput()
    stdout_thread = threading.Thread(target=_capture_stream, args=(process.stdout, spec.stdout_max_bytes, stdout_capture), daemon=True)
    stderr_thread = threading.Thread(target=_capture_stream, args=(process.stderr, spec.stderr_max_bytes, stderr_capture), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        process.wait(timeout=spec.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    if process.stdout is not None:
        process.stdout.close()
    if process.stderr is not None:
        process.stderr.close()

    if timed_out:
        execution_status = "timed_out"
    elif process.returncode == 0:
        execution_status = "succeeded"
    else:
        execution_status = "failed"
    return {
        "program_id": spec.program_id,
        "execution_status": execution_status,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "stdout": bytes(stdout_capture.data).decode("utf-8", errors="replace"),
        "stderr": bytes(stderr_capture.data).decode("utf-8", errors="replace"),
        "stdout_truncated": stdout_capture.truncated,
        "stderr_truncated": stderr_capture.truncated,
    }
