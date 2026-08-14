"""Persistent Runner-owned emergency stop for Worker submissions."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Iterator

from .config import RunnerConfig
from .errors import RunnerError
from .security import validate_controlled_write_path


class WorkerControlState:
    """Serialize pause/resume with new Worker admission and persist atomically."""

    def __init__(self, config: RunnerConfig):
        self._path = validate_controlled_write_path(
            config.runner_root / "state" / "workers.json", config,
        )
        self._lock = RLock()
        self._workers_paused = False
        self._load()

    @property
    def workers_paused(self) -> bool:
        with self._lock:
            return self._workers_paused

    @contextmanager
    def admit_submission(self) -> Iterator[None]:
        with self._lock:
            if self._workers_paused:
                raise RunnerError("WORKERS_PAUSED", "Worker submissions are paused")
            yield

    def pause(self) -> None:
        self._set_paused(True)

    def resume(self) -> None:
        self._set_paused(False)

    def _set_paused(self, value: bool) -> None:
        with self._lock:
            self._persist_locked(value)
            self._workers_paused = value

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._workers_paused = False
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or set(raw) != {"workers_paused"} or not isinstance(raw["workers_paused"], bool):
                    raise ValueError("invalid Worker control state")
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                self._workers_paused = True
                return
            self._workers_paused = raw["workers_paused"]

    def _persist_locked(self, value: bool) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            {"workers_paused": value}, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        temporary = self._path.with_name(f".{self._path.name}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise RunnerError("WORKER_STATE_PERSIST_FAILED", "Worker control state could not be persisted")
