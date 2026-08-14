"""General Direct Process Worker with frozen 7-Zip archive presets."""
from __future__ import annotations

import ntpath
import os
from pathlib import Path
from typing import Mapping

from .audit import append_job_audit_event
from .authority import AuthorityLevel, ExecutablePolicy, PRODUCTION_EXECUTABLE_CATALOG
from .config import RunnerConfig
from .errors import RunnerError
from .jobs import JobStore
from .models import ProcessJobSpec
from .process_supervisor import ProcessSupervisor
from .security import _is_reparse_point, validate_read_directory_path, validate_read_file_path


DIRECT_WORKER_OPERATIONS = frozenset({"archive.list", "archive.create"})
ARCHIVE_EXTENSION = ".zip"
DIRECT_JOB_TIMEOUT_SECONDS = 30
DIRECT_SOURCE_SCAN_MAX_ENTRIES = 10000


def _new_zip_path(value: object, config: RunnerConfig) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RunnerError("PATH_NOT_ALLOWED", "output archive path is not allowed")
    raw = value.replace("/", "\\")
    if raw.startswith(("\\\\", "\\\\?\\", "\\\\.\\")):
        raise RunnerError("PATH_NOT_ALLOWED", "output archive path is not allowed")
    drive, tail = ntpath.splitdrive(raw)
    root = config.read_root.resolve(strict=False)
    if drive.casefold() != "d:" or not tail.startswith("\\") or ":" in raw[2:] or any(part == ".." for part in tail.split("\\")):
        raise RunnerError("PATH_NOT_ALLOWED", "output archive path is not allowed")
    candidate = Path(ntpath.normpath(raw))
    try:
        relative = candidate.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise RunnerError("PATH_NOT_ALLOWED", "output archive path is outside D drive") from error
    current = root.absolute()
    for part in relative.parts:
        current = current / part
        if current.exists() and _is_reparse_point(current):
            raise RunnerError("PATH_NOT_ALLOWED", "output archive path crosses a reparse point")
    if candidate.suffix.casefold() != ARCHIVE_EXTENSION:
        raise RunnerError("ARCHIVE_FORMAT_NOT_ALLOWED", "only .zip archives are supported")
    if candidate.exists():
        raise RunnerError("OUTPUT_ALREADY_EXISTS", "output archive already exists")
    if not candidate.parent.is_dir():
        raise RunnerError("PATH_NOT_FOUND", "output archive parent was not found")
    return candidate.resolve(strict=False)


def _existing_zip_path(value: object, config: RunnerConfig) -> Path:
    archive_path = validate_read_file_path(value, config)
    if archive_path.suffix.casefold() != ARCHIVE_EXTENSION:
        raise RunnerError("ARCHIVE_FORMAT_NOT_ALLOWED", "only .zip archives are supported")
    return archive_path


def _source_path(value: object, config: RunnerConfig) -> Path:
    try:
        return validate_read_file_path(value, config)
    except RunnerError as file_error:
        if file_error.code not in {"NOT_A_REGULAR_FILE", "FILE_NOT_FOUND"}:
            raise
    directory = validate_read_directory_path(value, config)
    _validate_source_tree(directory)
    return directory


def _validate_source_tree(root: Path) -> None:
    """Do not let 7-Zip recurse through a descendant symlink or junction."""
    pending = [root]
    scanned = 0
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > DIRECT_SOURCE_SCAN_MAX_ENTRIES:
                        raise RunnerError("SOURCE_TREE_TOO_LARGE", "source directory exceeds Direct Worker scan limit")
                    child = Path(entry.path)
                    if _is_reparse_point(child):
                        raise RunnerError("PATH_NOT_ALLOWED", "source directory contains a reparse point")
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(child)
        except OSError as error:
            raise RunnerError("PATH_NOT_ALLOWED", "source directory could not be safely inspected") from error


def required_authority_for_operation(operation: object) -> AuthorityLevel:
    if operation == "archive.list":
        return AuthorityLevel.L1_READ_OPEN
    if operation == "archive.create":
        return AuthorityLevel.L2_CREATE_PROCESS
    raise RunnerError("OPERATION_NOT_ALLOWED", "Direct Worker operation is not allowed")


PROCESS_SPEC_FIELDS = frozenset({"type", "executable", "arguments", "cwd", "timeout", "write_scope", "network_policy"})


def process_job_spec_from_wire(value: object, config: RunnerConfig) -> ProcessJobSpec:
    if not isinstance(value, dict) or set(value) != PROCESS_SPEC_FIELDS or value.get("type") != "process":
        raise RunnerError("REQUEST_INVALID", "process job spec is invalid")
    executable = value.get("executable")
    arguments = value.get("arguments")
    timeout = value.get("timeout")
    write_scope = value.get("write_scope")
    network_policy = value.get("network_policy")
    if not isinstance(executable, str) or not executable or "\\" in executable or "/" in executable or ":" in executable:
        raise RunnerError("EXECUTABLE_NOT_ALLOWED", "executable must be a catalog ID")
    if not isinstance(arguments, list) or any(not isinstance(argument, str) for argument in arguments):
        raise RunnerError("PROCESS_SPEC_INVALID", "arguments must be a structured list")
    if not isinstance(timeout, int) or isinstance(timeout, bool):
        raise RunnerError("PROCESS_SPEC_INVALID", "timeout is invalid")
    if write_scope not in {"none", "workspace"} or network_policy not in {"none", "external"}:
        raise RunnerError("PROCESS_SPEC_INVALID", "scope or network policy is invalid")
    cwd = validate_read_directory_path(value.get("cwd"), config)
    return ProcessJobSpec("process", executable, tuple(arguments), cwd, timeout, write_scope, network_policy)


class DirectProcessWorkerService:
    """One structured worker for every catalogued executable; never accepts a shell command."""

    def __init__(
        self, config: RunnerConfig, *, store: JobStore | None = None, supervisor: ProcessSupervisor | None = None,
        catalog: Mapping[str, ExecutablePolicy] | None = None,
    ):
        self.config = config
        self.store = store or JobStore(config, audit_callback=append_job_audit_event)
        selected_catalog = PRODUCTION_EXECUTABLE_CATALOG if catalog is None else catalog
        self.supervisor = supervisor or ProcessSupervisor(self.store, config, catalog=selected_catalog)

    def submit_process_job(self, spec: ProcessJobSpec):
        if not isinstance(spec, ProcessJobSpec):
            raise RunnerError("PROCESS_SPEC_INVALID", "process job spec is invalid")
        validated = self._validate_executable_spec(spec)
        return self.supervisor.submit(validated, job_type="process")

    def submit_direct_job(self, operation: object, arguments: object):
        required_authority_for_operation(operation)
        if operation == "archive.list":
            archive_path = self._list_arguments(arguments)
            request = ProcessJobSpec("process", "7zip", ("l", "-ba", "-slt", str(archive_path)), self.config.read_root, DIRECT_JOB_TIMEOUT_SECONDS, "none", "none")
        elif operation == "archive.create":
            output_archive, source_paths = self._create_arguments(arguments)
            request = ProcessJobSpec("process", "7zip", ("a", "-tzip", "-bd", str(output_archive), *(str(path) for path in source_paths)), self.config.read_root, DIRECT_JOB_TIMEOUT_SECONDS, "none", "none")
        else:
            raise RunnerError("OPERATION_NOT_ALLOWED", "Direct Worker operation is not allowed")
        return self.supervisor.submit(request, job_type="direct")

    def _validate_executable_spec(self, spec: ProcessJobSpec) -> ProcessJobSpec:
        if spec.executable != "7zip":
            return spec
        if len(spec.arguments) == 4 and spec.arguments[:3] == ("l", "-ba", "-slt"):
            archive = _existing_zip_path(spec.arguments[3], self.config)
            return ProcessJobSpec(spec.type, spec.executable, (*spec.arguments[:3], str(archive)), spec.cwd, spec.timeout, spec.write_scope, spec.network_policy)
        if len(spec.arguments) >= 5 and spec.arguments[:3] == ("a", "-tzip", "-bd"):
            output = _new_zip_path(spec.arguments[3], self.config)
            sources = tuple(_source_path(value, self.config) for value in spec.arguments[4:])
            return ProcessJobSpec(spec.type, spec.executable, (*spec.arguments[:3], str(output), *(str(path) for path in sources)), spec.cwd, spec.timeout, spec.write_scope, spec.network_policy)
        raise RunnerError("OPERATION_NOT_ALLOWED", "7-Zip operation is not allowed")

    def _list_arguments(self, arguments: object) -> Path:
        if not isinstance(arguments, dict) or set(arguments) != {"archive_path"}:
            raise RunnerError("REQUEST_INVALID", "archive.list requires exactly archive_path")
        return _existing_zip_path(arguments["archive_path"], self.config)

    def _create_arguments(self, arguments: object) -> tuple[Path, tuple[Path, ...]]:
        if not isinstance(arguments, dict) or set(arguments) != {"source_paths", "output_archive"}:
            raise RunnerError("REQUEST_INVALID", "archive.create requires source_paths and output_archive")
        source_values = arguments["source_paths"]
        if not isinstance(source_values, list) or not 1 <= len(source_values) <= 20:
            raise RunnerError("REQUEST_INVALID", "source_paths must contain 1 to 20 explicit paths")
        sources = tuple(_source_path(value, self.config) for value in source_values)
        return _new_zip_path(arguments["output_archive"], self.config), sources


# Frozen import name retained; it refers to the single General Direct Process Worker.
DirectWorkerService = DirectProcessWorkerService
