import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.auth import sign_request
from jarvis_runner.cli import execute_signed_request
from jarvis_runner.config import RunnerConfig
from jarvis_runner.replay import ReplayCache


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name); self.key_path = root / "key"
        self.key = b"k" * 32; self.key_path.write_bytes(self.key)
        self.config = RunnerConfig(workspace_root=root, runner_root=root, audit_log=root / "audit.jsonl", read_root=root, auth_key_path=self.key_path)
    def tearDown(self): self.temp.cleanup()
    def request(self, **changes):
        now = datetime.now(timezone.utc); value = {"protocol_version":"1.0","request_id":str(uuid.uuid4()),"target_device":"windows-runner","action":"system.ping","arguments":{},"issued_at":now.isoformat(),"expires_at":(now + timedelta(minutes=1)).isoformat(),"nonce":"nonce-abcdefghijkl","key_id":"runner-local-v1"}; value.update(changes); value["signature"] = sign_request(value, self.key); return value
    def test_signed_request_and_replay(self):
        request = self.request(); cache = ReplayCache()
        self.assertEqual(execute_signed_request(request, self.config, cache).status, "success")
        self.assertEqual(execute_signed_request(request, self.config, cache).error_code, "REQUEST_REPLAYED")
    def test_tamper_and_auth_failure_do_not_execute(self):
        request = self.request(action="system.info"); request["action"] = "system.status"
        with patch("jarvis_runner.cli.execute_request") as execute:
            result = execute_signed_request(request, self.config, ReplayCache())
        self.assertEqual(result.error_code, "AUTH_FAILED"); execute.assert_not_called()
    def test_time_and_protocol_rejections(self):
        now = datetime.now(timezone.utc)
        expired = self.request(issued_at=(now-timedelta(minutes=2)).isoformat(), expires_at=(now-timedelta(minutes=1)).isoformat())
        self.assertEqual(execute_signed_request(expired, self.config, ReplayCache()).error_code, "REQUEST_EXPIRED")
        future = self.request(issued_at=(now+timedelta(seconds=31)).isoformat(), expires_at=(now+timedelta(minutes=1)).isoformat())
        self.assertEqual(execute_signed_request(future, self.config, ReplayCache()).error_code, "REQUEST_NOT_YET_VALID")
        invalid = self.request(request_id="not-a-uuid")
        self.assertEqual(execute_signed_request(invalid, self.config, ReplayCache()).error_code, "PROTOCOL_INVALID")
        too_long = self.request(expires_at=(now + timedelta(minutes=6)).isoformat())
        self.assertEqual(execute_signed_request(too_long, self.config, ReplayCache()).error_code, "PROTOCOL_INVALID")
        for field, value in (("protocol_version", "2.0"), ("target_device", "other-device"), ("key_id", "other-key")):
            rejected = self.request(**{field: value})
            self.assertEqual(execute_signed_request(rejected, self.config, ReplayCache()).error_code, "PROTOCOL_INVALID")
    def test_key_unavailable_and_bad_nonce(self):
        missing = RunnerConfig(**{**self.config.__dict__, "auth_key_path": self.key_path.with_name("missing")})
        self.assertEqual(execute_signed_request(self.request(), missing, ReplayCache()).error_code, "AUTH_KEY_UNAVAILABLE")
        invalid = self.request(nonce="bad")
        self.assertEqual(execute_signed_request(invalid, self.config, ReplayCache()).error_code, "PROTOCOL_INVALID")
        for key in (b"x" * 31, b"x" * 129):
            self.key_path.write_bytes(key)
            self.assertEqual(execute_signed_request(self.request(), self.config, ReplayCache()).error_code, "AUTH_KEY_UNAVAILABLE")
        self.key_path.write_bytes(self.key)

    def test_nonce_replay_and_concurrent_request_id(self):
        cache = ReplayCache(); first = self.request(nonce="nonce-unique-abcdef")
        second = self.request(nonce="nonce-unique-abcdef")
        self.assertEqual(execute_signed_request(first, self.config, cache).status, "success")
        self.assertEqual(execute_signed_request(second, self.config, cache).error_code, "REQUEST_REPLAYED")
        concurrent = self.request(); results = []
        def submit(): results.append(execute_signed_request(concurrent, self.config, cache).status)
        threads = [threading.Thread(target=submit) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(results.count("success"), 1)
        self.assertEqual(results.count("rejected"), 3)

    def test_signed_audit_redacts_request_material(self):
        request = self.request(arguments={})
        self.assertEqual(execute_signed_request(request, self.config, ReplayCache()).status, "success")
        record = (self.config.audit_log).read_text(encoding="utf-8")
        self.assertNotIn(request["signature"], record)
        self.assertNotIn(request["nonce"], record)
        self.assertNotIn(self.key.decode("ascii"), record)
