from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from .config import RunnerConfig
from .errors import RunnerError
from .security import _is_reparse_point, validate_read_file_path


FILE_EXPORT_MAX_BYTES = 16 * 1024 * 1024
FILE_EXPORT_CHUNK_BYTES = 64 * 1024


@dataclass
class PreparedFile:
    path: Path
    handle: object
    size: int
    initial_stat: os.stat_result


def _is_regular_handle(handle_stat: os.stat_result) -> bool:
    if not stat.S_ISREG(handle_stat.st_mode):
        return False
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return not bool(reparse and getattr(handle_stat, "st_file_attributes", 0) & reparse)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_identity(left, right) and left.st_size == right.st_size and left.st_mtime_ns == right.st_mtime_ns


def _raise_after_close(handle: object, error: RunnerError) -> None:
    try:
        handle.close()  # type: ignore[attr-defined]
    finally:
        raise error


def prepare_file(path: object, config: RunnerConfig) -> PreparedFile:
    """Validate, open, and return the one handle used for the export."""
    candidate = validate_read_file_path(path, config)
    try:
        before_open = os.stat(candidate, follow_symlinks=False)
    except FileNotFoundError as error:
        raise RunnerError("FILE_NOT_FOUND", "file was not found") from error
    except OSError as error:
        raise RunnerError("READ_FAILED", "file could not be inspected") from error
    if _is_reparse_point(candidate):
        raise RunnerError("PATH_NOT_ALLOWED", "path crosses a reparse point")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    try:
        descriptor = os.open(str(candidate), flags)
    except FileNotFoundError as error:
        raise RunnerError("FILE_NOT_FOUND", "file was not found") from error
    except IsADirectoryError as error:
        raise RunnerError("NOT_A_REGULAR_FILE", "path is not a regular file") from error
    except PermissionError as error:
        raise RunnerError("READ_FAILED", "file could not be opened") from error
    except OSError as error:
        raise RunnerError("READ_FAILED", "file could not be opened") from error

    handle = None
    try:
        handle = os.fdopen(descriptor, "rb", closefd=True)
        handle_stat = os.fstat(handle.fileno())
        if not _is_regular_handle(handle_stat):
            _raise_after_close(handle, RunnerError("NOT_A_REGULAR_FILE", "path is not a regular file"))
        if not _same_identity(before_open, handle_stat):
            _raise_after_close(handle, RunnerError("FILE_CHANGED", "file changed during open"))
        if not _same_snapshot(before_open, handle_stat):
            _raise_after_close(handle, RunnerError("FILE_CHANGED", "file changed during open"))
        if handle_stat.st_size > FILE_EXPORT_MAX_BYTES:
            error = RunnerError("FILE_TOO_LARGE", "file exceeds the fixed size limit")
            setattr(error, "file_size", int(handle_stat.st_size))
            _raise_after_close(handle, error)
        return PreparedFile(candidate, handle, handle_stat.st_size, handle_stat)
    except RunnerError:
        raise
    except OSError as error:
        try:
            if handle is not None:
                handle.close()
            else:
                os.close(descriptor)
        except OSError:
            pass
        raise RunnerError("READ_FAILED", "file could not be inspected") from error


def iter_file_chunks(prepared: PreparedFile):
    remaining = prepared.size
    while remaining:
        try:
            chunk = prepared.handle.read(min(FILE_EXPORT_CHUNK_BYTES, remaining))  # type: ignore[attr-defined]
        except OSError as error:
            raise RunnerError("READ_FAILED", "file read failed") from error
        if not chunk:
            raise RunnerError("FILE_CHANGED", "file changed during read")
        remaining -= len(chunk)
        yield chunk
    try:
        final_stat = os.fstat(prepared.handle.fileno())  # type: ignore[attr-defined]
    except OSError as error:
        raise RunnerError("READ_FAILED", "file could not be verified") from error
    if not _same_snapshot(prepared.initial_stat, final_stat):
        raise RunnerError("FILE_CHANGED", "file changed during read")
