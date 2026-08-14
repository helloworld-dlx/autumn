import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from jarvis_runner.cli import execute_request
from jarvis_runner.config import RunnerConfig
from jarvis_runner.models import ActionRequest


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name) / "JarvisWorkspace"
        self.config = RunnerConfig(workspace_root=root, runner_root=root / "JarvisRunner", audit_log=root / "JarvisRunner" / "logs" / "audit.jsonl")
    def tearDown(self): self.temp.cleanup()
    def test_ping_succeeds(self):
        result = execute_request(ActionRequest("a", "system.ping", {}, "test"), self.config)
        self.assertEqual(result.status, "success"); self.assertEqual(result.output["message"], "pong")
    def test_info_excludes_environment(self):
        result = execute_request(ActionRequest("b", "system.info", {}, "test"), self.config)
        self.assertEqual(result.status, "success"); self.assertNotIn("environment", result.output)
    def test_unapproved_action_is_not_executed(self):
        result = execute_request(ActionRequest("c", "cmd.execute", {}, "test"), self.config)
        self.assertEqual(result.status, "rejected"); self.assertEqual(result.error_code, "ACTION_NOT_ALLOWED")
    def test_audit_write_failure_fails_request(self):
        with patch("jarvis_runner.cli.append_audit_record", side_effect=OSError("private")):
            result = execute_request(ActionRequest("d", "system.ping", {}, "test"), self.config)
        self.assertEqual(result.status, "failed"); self.assertEqual(result.error_code, "AUDIT_LOG_FAILED")
