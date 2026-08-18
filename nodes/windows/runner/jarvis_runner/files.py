from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import RunnerConfig
from .errors import RunnerError
from .security import _is_reparse_point, validate_output, validate_read_directory_path
from .authority import EVERYTHING_EXECUTABLE_PATH


_EVERYTHING_RESULT_LIMIT = 20
_EVERYTHING_LITERAL_FORBIDDEN = frozenset('!|<>"*?')


def _integer(arguments: dict, name: str, default: int, configured_limit: int, *, allow_zero: bool = False) -> int:
    value = arguments.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < (0 if allow_zero else 1) or value > configured_limit:
        raise ValueError(f"invalid {name}")
    return value


def _only(arguments: dict, allowed: set[str]) -> None:
    if set(arguments) - allowed:
        raise ValueError("unknown action parameter")


def _entry_reparse(entry: os.DirEntry[str]) -> bool | None:
    try:
        if entry.is_symlink():
            return True
        is_junction = getattr(os.path, "isjunction", lambda _: False)
        if is_junction(entry.path):
            return True
        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(reparse and attributes & reparse)
    except PermissionError:
        return None
    except OSError:
        return None


def _item(entry: os.DirEntry[str]) -> dict | None:
    try:
        if entry.is_dir(follow_symlinks=False):
            kind, size = "directory", None
        elif entry.is_file(follow_symlinks=False):
            kind, size = "file", entry.stat(follow_symlinks=False).st_size
        else:
            return None
        modified = entry.stat(follow_symlinks=False).st_mtime
        absolute = Path(os.path.abspath(entry.path))
        return {"name": entry.name, "path": str(absolute), "kind": kind, "size_bytes": size, "modified_at": datetime.fromtimestamp(modified, timezone.utc).isoformat()}
    except (OSError, ValueError):
        return None


def _base(root: Path) -> dict:
    return {"search_root": str(root), "items": [], "returned_count": 0, "scanned_count": 0, "skipped_reparse_points": 0, "skipped_inaccessible": 0, "skipped_other": 0, "truncated": False, "stop_reason": "completed", "elapsed_ms": 0}


def _can_add(result: dict, item: dict, config: RunnerConfig) -> bool:
    trial = dict(result); trial["items"] = result["items"] + [item]; trial["returned_count"] = len(trial["items"])
    trial["scanned_count"] = max(config.list_directory_max_scanned_entries, config.search_max_scanned_entries)
    trial["skipped_reparse_points"] = trial["scanned_count"]
    trial["skipped_inaccessible"] = trial["scanned_count"]
    trial["skipped_other"] = trial["scanned_count"]
    trial["returned_count"] = max(trial["returned_count"], config.list_directory_max_results, config.search_max_results)
    trial["truncated"] = True; trial["stop_reason"] = "output_limit"; trial["elapsed_ms"] = 9223372036854775807
    try:
        validate_output(trial, config)
    except ValueError:
        return False
    return True


def _queued_directory(directory: Path, config: RunnerConfig) -> Path | None:
    root = config.read_root.absolute()
    try:
        relative = directory.absolute().relative_to(root)
    except ValueError:
        return None
    current = root
    if _is_reparse_point(current):
        return None
    for part in relative.parts:
        current = current / part
        if _is_reparse_point(current):
            return None
    return directory.absolute()


def worst_case_base_response(config: RunnerConfig) -> dict:
    result = _base(Path("D:\\"))
    prefix = "D:\\"
    segments = []
    remaining = max(0, config.maximum_argument_string_length - len(prefix))
    while remaining:
        segment_length = min(1, remaining)
        segments.append("a" * segment_length)
        remaining -= segment_length
        if remaining:
            segments.append("\\")
            remaining -= 1
    result["search_root"] = prefix + "".join(segments)
    result["scanned_count"] = max(config.list_directory_max_scanned_entries, config.search_max_scanned_entries)
    result["skipped_reparse_points"] = result["scanned_count"]
    result["skipped_inaccessible"] = result["scanned_count"]
    result["skipped_other"] = result["scanned_count"]
    result["returned_count"] = max(config.list_directory_max_results, config.search_max_results)
    result["truncated"] = True; result["stop_reason"] = "output_limit"
    result["elapsed_ms"] = 9223372036854775807
    return result


def _finish(result: dict, started: float, reason: str | None = None) -> dict:
    if reason:
        result["truncated"] = True; result["stop_reason"] = reason
    result["items"].sort(key=lambda item: item["path"].casefold())
    result["returned_count"] = len(result["items"])
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


def files_list_directory(arguments: dict, config: RunnerConfig) -> dict:
    _only(arguments, {"path", "max_results", "max_scanned_entries", "timeout_ms"})
    root = validate_read_directory_path(arguments.get("path"), config)
    max_results = _integer(arguments, "max_results", config.list_directory_max_results, config.list_directory_max_results)
    max_scanned = _integer(arguments, "max_scanned_entries", config.list_directory_max_scanned_entries, config.list_directory_max_scanned_entries)
    deadline = time.monotonic() + _integer(arguments, "timeout_ms", config.list_directory_timeout_ms, config.list_directory_timeout_ms) / 1000
    result = _base(root); started = time.monotonic()
    checked_root = _queued_directory(root, config)
    if checked_root is None:
        raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
    root = checked_root
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if time.monotonic() >= deadline: return _finish(result, started, "time_limit")
                if result["scanned_count"] >= max_scanned: return _finish(result, started, "scan_limit")
                result["scanned_count"] += 1
                entry_state = _entry_reparse(entry)
                if entry_state is True: result["skipped_reparse_points"] += 1; continue
                if entry_state is None: result["skipped_inaccessible"] += 1; continue
                item = _item(entry)
                if item is None: result["skipped_other"] += 1; continue
                if not _can_add(result, item, config): return _finish(result, started, "output_limit")
                result["items"].append(item)
                if len(result["items"]) >= max_results: return _finish(result, started, "result_limit")
    except PermissionError:
        raise RunnerError("FILE_SCAN_FAILED", "starting directory cannot be scanned")
    except OSError:
        raise RunnerError("FILE_SCAN_FAILED", "starting directory cannot be scanned")
    return _finish(result, started)


def _search_contract(arguments: dict, config: RunnerConfig) -> tuple[Path, str, set[str] | None, str, int, int, int, float]:
    _only(arguments, {"path", "query", "extensions", "kind", "max_depth", "max_results", "max_scanned_entries", "timeout_ms"})
    root = validate_read_directory_path(arguments.get("path"), config)
    query = arguments.get("query")
    if not isinstance(query, str) or not 1 <= len(query) <= 200 or any(char in query for char in ("\x00", "/", "\\", ":")):
        raise ValueError("invalid query")
    extensions_value = arguments.get("extensions")
    extensions: set[str] | None = None
    if extensions_value is not None:
        if not isinstance(extensions_value, list) or len(extensions_value) > 20: raise ValueError("invalid extensions")
        extensions = set()
        for extension in extensions_value:
            if not isinstance(extension, str) or not extension.startswith(".") or any(char in extension for char in ("/", "\\", ":", "\x00", "*", "?")):
                raise ValueError("invalid extension")
            extensions.add(extension.casefold())
    kind = arguments.get("kind", "file")
    if not isinstance(kind, str) or kind not in {"file", "directory", "any"}: raise ValueError("invalid kind")
    depth = _integer(arguments, "max_depth", config.search_max_depth, config.search_max_depth, allow_zero=True)
    results = _integer(arguments, "max_results", config.search_max_results, config.search_max_results)
    scanned = _integer(arguments, "max_scanned_entries", config.search_max_scanned_entries, config.search_max_scanned_entries)
    deadline = time.monotonic() + _integer(arguments, "timeout_ms", config.search_timeout_ms, config.search_timeout_ms) / 1000
    return root, query.casefold(), extensions, kind, depth, results, scanned, deadline


def _production_d_search(root: Path, config: RunnerConfig) -> bool:
    if str(config.read_root.absolute()).casefold() != "d:\\":
        return False
    try:
        root.absolute().relative_to(config.read_root.absolute())
    except ValueError:
        return False
    return True


def _everything_query(root: Path, query: str, kind: str) -> tuple[str, str | None]:
    if any(character in _EVERYTHING_LITERAL_FORBIDDEN for character in query):
        raise ValueError("invalid query")
    # Keep the search rooted by post-validating every result under ``root``.
    # Qualify the backend query by kind so a small bounded ES result window is
    # not filled by unrelated files before matching directories (or vice versa).
    kind_term = {"file": "file:", "directory": "folder:"}.get(kind, "")
    primary = f"{kind_term}{query}"
    words = tuple(word for word in query.split() if word)
    if len(words) > 1:
        fallback_terms = words
    elif len(query) >= 4:
        midpoint = len(query) // 2
        fallback_terms = (query[:midpoint], query[midpoint:])
    else:
        fallback_terms = ()
    fallback = f"{kind_term}{' '.join(fallback_terms)}" if fallback_terms else None
    return primary, fallback


def _everything_item(path_text: str, root: Path, config: RunnerConfig) -> dict | None:
    candidate = Path(os.path.abspath(path_text))
    try:
        candidate.relative_to(root.absolute())
    except ValueError:
        return None
    if _queued_directory(candidate.parent, config) is None or _is_reparse_point(candidate):
        return None
    try:
        details = candidate.stat(follow_symlinks=False)
        mode = details.st_mode
        if stat.S_ISDIR(mode):
            kind, size = "directory", None
        elif stat.S_ISREG(mode):
            kind, size = "file", details.st_size
        else:
            return None
        return {"name": candidate.name, "path": str(candidate), "kind": kind, "size_bytes": size, "modified_at": datetime.fromtimestamp(details.st_mtime, timezone.utc).isoformat()}
    except OSError:
        return None


def _everything_search(root: Path, query: str, kind: str, extensions: set[str] | None, max_results: int, deadline: float, config: RunnerConfig) -> dict:
    if EVERYTHING_EXECUTABLE_PATH is None or not EVERYTHING_EXECUTABLE_PATH.is_file():
        raise RunnerError("EVERYTHING_UNAVAILABLE", "D: filename search backend is unavailable")
    primary, fallback = _everything_query(root, query, kind)
    result = _base(root); started = time.monotonic(); result_limit = min(max_results, _EVERYTHING_RESULT_LIMIT)
    for search_text in (primary, fallback):
        if search_text is None:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return _finish(result, started, "time_limit")
        try:
            completed = subprocess.run(
                [str(EVERYTHING_EXECUTABLE_PATH), "-n", str(result_limit), "-s", "-full-path-and-name", search_text],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="strict", shell=False, cwd=str(config.read_root), timeout=remaining,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as error:
            raise RunnerError("EVERYTHING_UNAVAILABLE", "D: filename search backend is unavailable") from error
        if completed.returncode != 0:
            raise RunnerError("EVERYTHING_UNAVAILABLE", "D: filename search backend is unavailable")
        for line in completed.stdout.splitlines():
            result["scanned_count"] += 1
            item = _everything_item(line, root, config)
            if item is None or (kind != "any" and item["kind"] != kind):
                continue
            if extensions is not None and (item["kind"] != "file" or Path(item["name"]).suffix.casefold() not in extensions):
                continue
            if not _can_add(result, item, config):
                return _finish(result, started, "output_limit")
            result["items"].append(item)
            if len(result["items"]) >= result_limit:
                return _finish(result, started, "result_limit")
        if result["items"] or fallback is None:
            return _finish(result, started)
    return _finish(result, started)


def files_search(arguments: dict, config: RunnerConfig) -> dict:
    root, query, extensions, kind, max_depth, max_results, max_scanned, deadline = _search_contract(arguments, config)
    if _production_d_search(root, config):
        return _everything_search(root, query, kind, extensions, max_results, deadline, config)
    result = _base(root); started = time.monotonic(); stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        if time.monotonic() >= deadline: return _finish(result, started, "time_limit")
        directory, depth = stack.pop()
        checked_directory = _queued_directory(directory, config)
        if checked_directory is None:
            if depth == 0:
                raise RunnerError("PATH_NOT_ALLOWED", "path is not allowed")
            result["skipped_reparse_points"] += 1
            continue
        directory = checked_directory
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if time.monotonic() >= deadline: return _finish(result, started, "time_limit")
                    if result["scanned_count"] >= max_scanned: return _finish(result, started, "scan_limit")
                    result["scanned_count"] += 1
                    entry_state = _entry_reparse(entry)
                    if entry_state is True: result["skipped_reparse_points"] += 1; continue
                    if entry_state is None: result["skipped_inaccessible"] += 1; continue
                    item = _item(entry)
                    if item is None: result["skipped_other"] += 1; continue
                    if item["kind"] == "directory" and depth < max_depth: stack.append((Path(entry.path), depth + 1))
                    if query not in item["name"].casefold() or (kind != "any" and item["kind"] != kind): continue
                    if extensions is not None and (item["kind"] != "file" or Path(item["name"]).suffix.casefold() not in extensions): continue
                    if not _can_add(result, item, config): return _finish(result, started, "output_limit")
                    result["items"].append(item)
                    if len(result["items"]) >= max_results: return _finish(result, started, "result_limit")
        except PermissionError:
            if directory == root: raise RunnerError("FILE_SCAN_FAILED", "starting directory cannot be scanned")
            result["skipped_inaccessible"] += 1
        except OSError:
            if directory == root: raise RunnerError("FILE_SCAN_FAILED", "starting directory cannot be scanned")
            result["skipped_other"] += 1
    return _finish(result, started)
