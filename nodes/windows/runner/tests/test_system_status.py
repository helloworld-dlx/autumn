import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.cli import execute_request
from jarvis_runner.config import RunnerConfig
from jarvis_runner.models import ActionRequest
from jarvis_runner.security import validate_output
from jarvis_runner import system_status


class SystemStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.config = RunnerConfig(workspace_root=root, runner_root=root, audit_log=root / "audit.jsonl", read_root=root)
    def tearDown(self): self.temp.cleanup()
    def test_status_contract_and_no_sensitive_fields(self):
        result = execute_request(ActionRequest("status", "system.status", {}, "test"), self.config)
        self.assertEqual(result.status, "success"); validate_output(result.output, self.config)
        self.assertTrue(result.output["online"]); self.assertGreaterEqual(result.output["cpu_percent"], 0.0); self.assertLessEqual(result.output["cpu_percent"], 100.0)
        self.assertEqual(set(result.output), {"online", "collected_at", "cpu_percent", "memory", "d_drive", "battery", "uptime_seconds", "python_version"})
        self.assertNotIn("environment", result.output); self.assertNotIn("processes", result.output)
    def test_status_rejects_nonempty_arguments(self):
        result = execute_request(ActionRequest("status-args", "system.status", {"extra": True}, "test"), self.config)
        self.assertEqual((result.status, result.error_code), ("rejected", "REQUEST_INVALID"))

    def test_large_tick_count_is_not_truncated(self):
        with patch.object(system_status._KERNEL32, "GetTickCount64", return_value=2**32 + 5000), patch("jarvis_runner.system_status._cpu_percent", return_value=1.0), patch("jarvis_runner.system_status._memory", return_value={"total_bytes": 1, "available_bytes": 1, "used_bytes": 0, "percent": 0.0}), patch("jarvis_runner.system_status._battery", return_value={"present": False, "percent": None, "charging": None, "ac_online": None}):
            result = system_status.system_status(self.config)
        self.assertEqual(result["uptime_seconds"], (2**32 + 5000) // 1000)

    def test_unknown_battery_percent_is_null(self):
        power = system_status._SYSTEM_POWER_STATUS(); power.BatteryFlag = 0; power.BatteryLifePercent = 255; power.ACLineStatus = 1
        def fill(pointer): pointer._obj.ACLineStatus = power.ACLineStatus; pointer._obj.BatteryFlag = power.BatteryFlag; pointer._obj.BatteryLifePercent = power.BatteryLifePercent; return 1
        with patch.object(system_status._KERNEL32, "GetSystemPowerStatus", side_effect=fill):
            result = system_status._battery()
        self.assertIsNone(result["percent"])
