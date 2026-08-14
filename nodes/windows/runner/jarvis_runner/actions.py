from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import RunnerConfig


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def system_ping(config: RunnerConfig) -> dict:
    return {"message": "pong", "timestamp": utc_now(), "runner_version": config.runner_version}


def system_info(config: RunnerConfig) -> dict:
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "process_id": os.getpid(),
        "current_working_directory": str(Path.cwd()),
        "runner_root": str(config.runner_root),
    }
