import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jarvis_runner.audit import append_audit_record, append_codex_start_rejected_audit, append_runner_started_audit
from jarvis_runner.config import RunnerConfig
from jarvis_runner.models import ActionRequest, ActionResult


class AuditTests(unittest.TestCase):
    def _config(self, root: Path, audit_max_bytes: int = 4096, audit_backup_count: int = 3) -> RunnerConfig:
        runner_root = root / "JarvisRunner"
        return RunnerConfig(
            workspace_root=root,
            runner_root=runner_root,
            audit_log=runner_root / "logs" / "audit.jsonl",
            audit_max_bytes=audit_max_bytes,
            audit_backup_count=audit_backup_count,
        )

    def _request(self, request_id: str, arguments: dict | None = None, requested_by: str = "test") -> ActionRequest:
        return ActionRequest(request_id, "system.ping", arguments or {}, requested_by)

    def _result(self, request_id: str, output: dict | None = None) -> ActionResult:
        return ActionResult(request_id, "system.ping", "success", output or {"ignored": "output"}, None, None, "a", "b")

    def _read_rows(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_audit_appends_and_redacts(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp))
            request = self._request("one", {"secret": "hidden"})
            result = self._result("one")
            append_audit_record(request, result, config)
            append_audit_record(request, result, config)
            rows = self._read_rows(config.audit_log)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["arguments"]["secret"], "[REDACTED]")
            self.assertNotIn("output", rows[0])

    def test_signed_arguments_are_redacted_as_a_whole(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp))
            request = self._request("signed", {"real": "signed-argument-secret"}, "signed-protocol")
            append_audit_record(request, self._result("signed"), config)
            row = self._read_rows(config.audit_log)[0]
            self.assertEqual(row["arguments"], "[SIGNED_REQUEST_REDACTED]")
            self.assertNotIn("signed-argument-secret", config.audit_log.read_text(encoding="utf-8"))

    def test_runner_identity_and_process_spec_diagnostics_contain_only_safe_values(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp))
            append_runner_started_audit(
                123, r"C:\Python\python.exe", Path(r"D:\JarvisWorkspace\JarvisRunner\jarvis_runner"),
                Path(r"D:\JarvisWorkspace\JarvisRunner\jarvis_runner\authority.py"),
                Path(r"D:\JarvisWorkspace\JarvisRunner\jarvis_runner\codex_worker.py"),
                1800, 800, config,
            )
            error = type("SafeAdmissionError", (Exception,), {"code": "PROCESS_SPEC_INVALID"})("secret prompt")
            append_codex_start_rejected_audit(
                "job-1", error, config, argv_count=30, max_arg_length=1048,
                allowed_max_arg_length=1800, timeout=60,
            )
            rows = self._read_rows(config.audit_log)
            self.assertEqual(rows[0]["action"], "runner_started")
            self.assertEqual(rows[0]["codex_argv_single_item_limit"], 1800)
            self.assertEqual(rows[1]["first_failing_rule"], None)
            self.assertEqual(rows[1]["max_arg_length"], 1048)
            raw = config.audit_log.read_text(encoding="utf-8")
            self.assertNotIn("secret prompt", raw)
            self.assertNotIn("token", raw.casefold())

    def test_does_not_rotate_before_threshold(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp), audit_max_bytes=4096)
            for index in range(3):
                request_id = f"before-{index}"
                append_audit_record(self._request(request_id), self._result(request_id), config)
            self.assertLessEqual(config.audit_log.stat().st_size, config.audit_max_bytes)
            self.assertFalse(config.audit_log.with_name("audit.jsonl.1").exists())
            for row in self._read_rows(config.audit_log):
                self.assertIn("request_id", row)

    def test_rotates_when_record_would_exceed_threshold(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp), audit_max_bytes=256)
            append_audit_record(self._request("old"), self._result("old"), config)
            append_audit_record(self._request("new"), self._result("new"), config)
            backup = config.audit_log.with_name("audit.jsonl.1")
            self.assertTrue(config.audit_log.exists())
            self.assertTrue(backup.exists())
            self.assertEqual(self._read_rows(backup)[0]["request_id"], "old")
            self.assertEqual(self._read_rows(config.audit_log)[0]["request_id"], "new")
            for path in (config.audit_log, backup):
                for line in path.read_text(encoding="utf-8").splitlines():
                    json.loads(line)

    def test_multiple_rotations_keep_only_configured_backups(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp), audit_max_bytes=256, audit_backup_count=3)
            for index in range(1, 7):
                request_id = f"rotation-{index}"
                append_audit_record(self._request(request_id), self._result(request_id), config)
            self.assertEqual(self._read_rows(config.audit_log)[0]["request_id"], "rotation-6")
            self.assertEqual(self._read_rows(config.audit_log.with_name("audit.jsonl.1"))[0]["request_id"], "rotation-5")
            self.assertEqual(self._read_rows(config.audit_log.with_name("audit.jsonl.3"))[0]["request_id"], "rotation-3")
            self.assertFalse(config.audit_log.with_name("audit.jsonl.4").exists())
            self.assertTrue(config.audit_log.with_name("audit.jsonl.2").exists())

    def test_oversized_record_leaves_existing_log_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp), audit_max_bytes=256)
            append_audit_record(self._request("original"), self._result("original"), config)
            before = config.audit_log.read_bytes()
            oversized = self._request("oversized", {"safe": "x" * 1000})
            with self.assertRaises(ValueError):
                append_audit_record(oversized, self._result("oversized"), config)
            self.assertEqual(config.audit_log.read_bytes(), before)
            for index in range(1, 4):
                self.assertFalse(config.audit_log.with_name(f"audit.jsonl.{index}").exists())

    def test_concurrent_appends_are_complete_unique_json_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp), audit_max_bytes=64 * 1024)

            def write(index: int) -> None:
                request_id = f"concurrent-{index}"
                append_audit_record(self._request(request_id), self._result(request_id), config)

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(write, range(100)))
            rows = self._read_rows(config.audit_log)
            request_ids = [row["request_id"] for row in rows]
            self.assertEqual(len(rows), 100)
            self.assertEqual(len(set(request_ids)), 100)
            self.assertEqual(set(request_ids), {f"concurrent-{index}" for index in range(100)})

    def test_current_and_backup_logs_do_not_contain_sensitive_values_or_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp), audit_max_bytes=512, audit_backup_count=3)
            unsafe_values = (
                "TEST_KEY_VALUE",
                "TEST_SIGNATURE_VALUE",
                "TEST_NONCE_VALUE",
                "ACTION_OUTPUT_UNSAFE",
                "SEARCH_RESULT_UNSAFE",
                "SIGNED_ARGUMENT_UNSAFE",
            )
            for index in range(6):
                requested_by = "test" if index % 2 == 0 else "signed-protocol"
                request = self._request(
                    f"sensitive-{index}",
                    {"secret": unsafe_values[0]} if requested_by == "test" else {
                        "signature": unsafe_values[1],
                        "nonce": unsafe_values[2],
                        "arguments": unsafe_values[5],
                    },
                    requested_by,
                )
                result = self._result(f"sensitive-{index}", {"output": unsafe_values[3], "results": [unsafe_values[4]]})
                append_audit_record(request, result, config)
            paths = [config.audit_log] + [config.audit_log.with_name(f"audit.jsonl.{index}") for index in range(1, 4)]
            existing_paths = [path for path in paths if path.exists()]
            self.assertGreaterEqual(len(existing_paths), 2)
            for path in existing_paths:
                raw = path.read_text(encoding="utf-8")
                for unsafe_value in unsafe_values:
                    self.assertNotIn(unsafe_value, raw)
                for line in raw.splitlines():
                    row = json.loads(line)
                    self.assertNotIn("output", row)
                    self.assertNotIn("results", row)

    def test_invalid_result_status_is_rejected(self):
        with self.assertRaises(ValueError):
            ActionResult("x", "system.ping", "unknown", {}, None, None, "a", "b")
