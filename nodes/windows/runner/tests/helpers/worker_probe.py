"""Test-only subprocess probe. It is never present in the production catalog."""
from __future__ import annotations

import subprocess
import sys
import time


def main(argv: list[str]) -> int:
    mode = argv[1]
    if mode == "success":
        print("hello")
        return 0
    if mode == "empty":
        return 0
    if mode == "fail":
        print("failed", file=sys.stderr)
        return 7
    if mode == "sleep":
        time.sleep(float(argv[2]))
        return 0
    if mode == "output":
        size = int(argv[2])
        print("o" * size)
        print("e" * size, file=sys.stderr)
        return 0
    if mode == "spawn-child":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], shell=False)
        print(child.pid, flush=True)
        time.sleep(60)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
