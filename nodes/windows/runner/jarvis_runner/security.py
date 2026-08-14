from __future__ import annotations

import json
import ntpath
import os
import re
import stat
from pathlib import Path
from typing import Any

from .config import RunnerConfig
from .errors import OutputValidationError, RunnerError


_ACTION_RE = re.compile(r"^[a-z0-9._]+$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_SENSITIVE_KEYS = {"token", "password", "secret", "authorization", "cookie", "api_key"}


def validate_action_name(action: object) -> str:
    if not isinstance(action, str) or not _ACTION_RE.fullmatch(action):
        raise ValueError("invalid action name")
    return action


def validate_request_id(request_id: object) -> str:
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.fullmatch(request_id):
        raise ValueError("invalid request_id")
    return request_id


def _validate_json_object(value: object, config: RunnerConfig, *, top_level_name: str, string_limit: int, json_limit: int, node_limit: int) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{top_level_name} must be a dict")

    nodes = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > node_limit:
            raise ValueError(f"{top_level_name} exceed maximum node count")
        if depth > config.maximum_argument_depth:
            raise ValueError(f"{top_level_name} exceed maximum nesting depth")
        if isinstance(item, bytes):
            raise ValueError(f"bytes are not allowed in {top_level_name}")
        if isinstance(item, str):
            if len(item) > string_limit:
                raise ValueError(f"{top_level_name} string exceeds maximum length")
            return
        if item is None or isinstance(item, (bool, int, float)):
            return
        if isinstance(item, dict):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise ValueError(f"{top_level_name} object keys must be strings")
                visit(key, depth + 1)
                visit(nested, depth + 1)
            return
        if isinstance(item, list):
            for nested in item:
                visit(nested, depth + 1)
            return
        raise ValueError(f"{top_level_name} value is not JSON compatible")

    visit(value, 0)
    try:
        serialized = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{top_level_name} are not JSON serializable") from error
    if len(serialized) > json_limit:
        raise ValueError(f"{top_level_name} exceed maximum JSON length")
    return value


def validate_arguments(arguments: object, config: RunnerConfig) -> dict:
    return _validate_json_object(
        arguments, config, top_level_name="arguments",
        string_limit=config.maximum_argument_string_length,
        json_limit=config.maximum_argument_json_length,
        node_limit=config.maximum_argument_nodes,
    )


def validate_output(output: object, config: RunnerConfig) -> dict:
    try:
        return _validate_json_object(
            output, config, top_level_name="output",
            string_limit=config.maximum_output_string_length,
            json_limit=config.maximum_output_json_length,
            node_limit=config.maximum_output_nodes,
        )
    except ValueError as error:
        raise OutputValidationError("output is invalid") from error


def _contains_external_reparse_point(raw_path: Path, workspace_root: Path) -> bool:
    try:
        relative = raw_path.absolute().relative_to(workspace_root.absolute())
    except ValueError:
        return False
    current = workspace_root.absolute()
    for part in relative.parts:
        current = current / part
        if not current.exists():
            continue
        attributes = getattr(current.stat(), "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        if current.is_symlink() or (reparse and attributes & reparse):
            try:
                current.resolve(strict=True).relative_to(workspace_root.resolve(strict=True))
            except ValueError:
                return True
    return False


def validate_controlled_write_path(path: str | Path, config: RunnerConfig) -> Path:
    raw_path = Path(path)
    candidate = raw_path.resolve(strict=False)
    root = config.workspace_root.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("controlled write path is outside workspace_root") from error
    if _contains_external_reparse_point(raw_path, config.workspace_root):
        raise ValueError("controlled write path crosses an external reparse point")
    return candidate


def _is_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", lambda _: False)
    if is_junction(path):
        return True
    try:
        attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def validate_read_directory_path(path: object, config: RunnerConfig) -> Path:
    if not isinstance(path, str) or not path or "\x00" in path:
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    raw = path.replace("/", "\\")
    if raw.startswith("\\\\") or raw.startswith("\\\\?\\") or raw.startswith("\\\\.\\"):
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    drive, tail = ntpath.splitdrive(raw)
    root = config.read_root.resolve(strict=False)
    if not drive or drive.casefold() != root.drive.casefold() or not tail.startswith("\\") or ":" in raw[2:]:
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    if any(part == ".." for part in tail.split("\\")):
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    raw_path = Path(ntpath.normpath(raw))
    try:
        relative = raw_path.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise RunnerError("PATH_NOT_ALLOWED", "path is outside read root") from error
    current = root.absolute()
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            raise RunnerError("PATH_NOT_ALLOWED", "path crosses a reparse point")
    candidate = raw_path.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise RunnerError("PATH_NOT_ALLOWED", "path is outside read root") from error
    if not candidate.exists():
        raise RunnerError("PATH_NOT_FOUND", "path was not found")
    if not candidate.is_dir():
        raise RunnerError("PATH_NOT_DIRECTORY", "path is not a directory")
    return candidate


def validate_read_file_path(path: object, config: RunnerConfig) -> Path:
    """Validate one ordinary file using the existing read-root policy."""
    if not isinstance(path, str) or not path or "\x00" in path:
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    raw = path.replace("/", "\\")
    if raw.startswith("\\\\") or raw.startswith("\\\\?\\") or raw.startswith("\\\\.\\"):
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    drive, tail = ntpath.splitdrive(raw)
    root = config.read_root.resolve(strict=False)
    if not drive or drive.casefold() != root.drive.casefold() or not tail.startswith("\\") or ":" in raw[2:]:
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    if any(part == ".." for part in tail.split("\\")):
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")

    raw_path = Path(ntpath.normpath(raw))
    try:
        relative = raw_path.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise RunnerError("PATH_NOT_ALLOWED", "path is outside read root") from error
    current = root.absolute()
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            raise RunnerError("PATH_NOT_ALLOWED", "path crosses a reparse point")

    candidate = raw_path.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise RunnerError("PATH_NOT_ALLOWED", "path is outside read root") from error
    try:
        exists = candidate.exists()
        is_file = candidate.is_file()
    except OSError as error:
        raise RunnerError("READ_FAILED", "file could not be inspected") from error
    if not exists:
        raise RunnerError("FILE_NOT_FOUND", "file was not found")
    if not is_file:
        raise RunnerError("NOT_A_REGULAR_FILE", "path is not a regular file")
    return candidate


def redact_for_audit(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.casefold() in _SENSITIVE_KEYS else redact_for_audit(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_for_audit(item) for item in value]
    return value
