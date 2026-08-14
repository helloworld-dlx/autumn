import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.config import RunnerConfig
from jarvis_runner.security import redact_for_audit, validate_action_name, validate_arguments, validate_controlled_write_path, validate_output, validate_request_id


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name) / "JarvisWorkspace"
        self.config = RunnerConfig(workspace_root=root, runner_root=root / "JarvisRunner", audit_log=root / "JarvisRunner" / "logs" / "audit.jsonl")

    def tearDown(self): self.temp.cleanup()

    def test_controlled_path_is_allowed(self):
        self.assertEqual(validate_controlled_write_path(self.config.workspace_root / "x.txt", self.config), self.config.workspace_root / "x.txt")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError): validate_controlled_write_path(self.config.workspace_root / ".." / "outside.txt", self.config)

    def test_prefix_twin_is_rejected(self):
        with self.assertRaises(ValueError): validate_controlled_write_path(str(self.config.workspace_root) + "2/x.txt", self.config)

    def test_external_reparse_point_is_rejected(self):
        self.config.workspace_root.mkdir(parents=True)
        outside = Path(self.temp.name) / "outside"; outside.mkdir()
        link = self.config.workspace_root / "linked"
        try:
            import os
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            with patch("jarvis_runner.security._contains_external_reparse_point", return_value=True):
                with self.assertRaises(ValueError): validate_controlled_write_path(self.config.workspace_root / "future.txt", self.config)
        else:
            with self.assertRaises(ValueError): validate_controlled_write_path(link / "future.txt", self.config)

    def test_argument_length_and_depth_are_limited(self):
        with self.assertRaises(ValueError): validate_arguments({"x": "a" * 1001}, self.config)
        value = {}; cursor = value
        for _ in range(10): cursor["x"] = {}; cursor = cursor["x"]
        with self.assertRaises(ValueError): validate_arguments(value, self.config)

    def test_key_nodes_and_json_size_are_limited(self):
        with self.assertRaises(ValueError): validate_arguments({"k" * 1001: "x"}, self.config)
        with self.assertRaises(ValueError): validate_arguments({str(i): "x" for i in range(600)}, self.config)
        small = RunnerConfig(**{**self.config.__dict__, "maximum_argument_json_length": 10})
        with self.assertRaises(ValueError): validate_arguments({"x": "long"}, small)

    def test_output_limits_and_json_safety(self):
        with self.assertRaises(ValueError): validate_output({"x": "a" * 10001}, self.config)
        with self.assertRaises(ValueError): validate_output({"x": float("nan")}, self.config)
        small = RunnerConfig(**{**self.config.__dict__, "maximum_output_json_length": 10})
        with self.assertRaises(ValueError): validate_output({"x": "long"}, small)

    def test_action_and_request_id_validation(self):
        self.assertEqual(validate_action_name("system.ping"), "system.ping")
        self.assertEqual(validate_request_id("abc-123_x"), "abc-123_x")
        with self.assertRaises(ValueError): validate_action_name("System Ping")
        with self.assertRaises(ValueError): validate_request_id("bad id")

    def test_redaction_is_recursive(self):
        self.assertEqual(redact_for_audit({"token": "x", "list": [{"api_key": "y"}]}), {"token": "[REDACTED]", "list": [{"api_key": "[REDACTED]"}]})
