from __future__ import annotations

import ctypes
import shutil
import sys
import time
from datetime import datetime, timezone

from .config import RunnerConfig


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
_KERNEL32.GetSystemTimes.argtypes = [ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME)]
_KERNEL32.GetSystemTimes.restype = ctypes.c_int
_KERNEL32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
_KERNEL32.GlobalMemoryStatusEx.restype = ctypes.c_int
_KERNEL32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(_SYSTEM_POWER_STATUS)]
_KERNEL32.GetSystemPowerStatus.restype = ctypes.c_int
_KERNEL32.GetTickCount64.argtypes = []
_KERNEL32.GetTickCount64.restype = ctypes.c_ulonglong


def _filetime_value(value: _FILETIME) -> int:
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


def _cpu_sample() -> tuple[int, int]:
    idle = _FILETIME(); kernel = _FILETIME(); user = _FILETIME()
    if not _KERNEL32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        raise RuntimeError("cpu status unavailable")
    return _filetime_value(idle), _filetime_value(kernel) + _filetime_value(user)


def _cpu_percent() -> float:
    idle_before, total_before = _cpu_sample()
    time.sleep(0.2)
    idle_after, total_after = _cpu_sample()
    total_delta = total_after - total_before
    if total_delta <= 0:
        raise RuntimeError("cpu status unavailable")
    return round(max(0.0, min(100.0, 100.0 * (1.0 - (idle_after - idle_before) / total_delta))), 1)


def _memory() -> dict:
    status = _MEMORYSTATUSEX(); status.dwLength = ctypes.sizeof(status)
    if not _KERNEL32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise RuntimeError("memory status unavailable")
    total, available = int(status.ullTotalPhys), int(status.ullAvailPhys)
    used = total - available
    return {"total_bytes": total, "available_bytes": available, "used_bytes": used, "percent": round(0.0 if total == 0 else used * 100.0 / total, 1)}


def _battery() -> dict:
    power = _SYSTEM_POWER_STATUS()
    if not _KERNEL32.GetSystemPowerStatus(ctypes.byref(power)):
        raise RuntimeError("power status unavailable")
    present = not bool(power.BatteryFlag & 128)
    ac_online = {0: False, 1: True}.get(power.ACLineStatus)
    if not present:
        return {"present": False, "percent": None, "charging": None, "ac_online": ac_online}
    percent = None if power.BatteryLifePercent == 255 else int(power.BatteryLifePercent)
    charging = None if power.BatteryFlag == 255 else bool(power.BatteryFlag & 8)
    return {"present": True, "percent": percent, "charging": charging, "ac_online": ac_online}


def system_status(config: RunnerConfig) -> dict:
    memory = _memory()
    disk = shutil.disk_usage(config.read_root)
    total, free = int(disk.total), int(disk.free)
    used = total - free
    uptime = int(_KERNEL32.GetTickCount64())
    return {"online": True, "collected_at": datetime.now(timezone.utc).isoformat(), "cpu_percent": _cpu_percent(), "memory": memory, "d_drive": {"total_bytes": total, "free_bytes": free, "used_bytes": used, "percent": round(0.0 if total == 0 else used * 100.0 / total, 1)}, "battery": _battery(), "uptime_seconds": uptime // 1000, "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"}
