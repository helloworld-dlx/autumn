import http.client
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.auth import sign_request
from jarvis_runner.config import RunnerConfig
from jarvis_runner.network import FILE_AUTH_HEADERS, TailscaleHTTPServer
from jarvis_runner.replay import ReplayCache


class FileExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r"D:\JarvisWorkspace\JarvisRunner\work")
        self.root = Path(self.temp.name)
        self.key = b"f" * 32
        self.key_path = self.root / "key"
        self.key_path.write_bytes(self.key)
        self.config = RunnerConfig(
            workspace_root=self.root,
            runner_root=self.root,
            audit_log=self.root / "audit.jsonl",
            job_state_path=self.root / "state" / "jobs.json",
            read_root=Path("D:\\"),
            auth_key_path=self.key_path,
            listen_host="100.101.102.103",
            allowed_task_clients=("100.101.102.104",),
        )
        self.server = TailscaleHTTPServer(("127.0.0.1", 0), self.config, ReplayCache())
        self.server.client_ip_override = "100.101.102.104"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def signed_headers(self, path, **changes):
        now = datetime.now(timezone.utc)
        request = {
            "protocol_version": "1.0",
            "request_id": str(uuid.uuid4()),
            "target_device": "windows-runner",
            "action": "file.export",
            "arguments": {"path": path},
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=1)).isoformat(),
            "nonce": "nonce-" + uuid.uuid4().hex,
            "key_id": "runner-local-v1",
        }
        request.update(changes)
        request["signature"] = sign_request(request, self.key)
        return {FILE_AUTH_HEADERS[key]: request[key] for key in FILE_AUTH_HEADERS}

    def signed_task(self, action, arguments):
        now = datetime.now(timezone.utc)
        request = {
            "protocol_version": "1.0",
            "request_id": str(uuid.uuid4()),
            "target_device": "windows-runner",
            "action": action,
            "arguments": arguments,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=1)).isoformat(),
            "nonce": "task-" + uuid.uuid4().hex,
            "key_id": "runner-local-v1",
        }
        request["signature"] = sign_request(request, self.key)
        return request

    def call(self, path, body, headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        connection.request("POST", path, body, headers)
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def call_file(self, file_path, headers=None):
        return self.call(
            "/v1/file",
            json.dumps({"path": str(file_path)}).encode("utf-8"),
            {"Content-Type": "application/json", **(headers or self.signed_headers(str(file_path)))},
        )

    def error_code(self, response_body):
        return json.loads(response_body.decode("utf-8"))["error_code"]

    def test_small_and_zero_byte_files_stream_exactly(self):
        small = self.root / "small.txt"
        expected = (bytes(range(256)) * 700) + b"\x00tail"
        small.write_bytes(expected)
        status, headers, body = self.call_file(small)
        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(headers["X-Autumn-Filename"], "small.txt")
        self.assertEqual(headers["X-Autumn-Size"], str(len(expected)))
        for _ in range(50):
            if self.config.audit_log.exists():
                break
            time.sleep(0.01)
        audit = self.config.audit_log.read_text(encoding="utf-8")
        self.assertIn('"action":"file.export"', audit)
        self.assertIn(f'"file_size_bytes":{len(expected)}', audit)
        self.assertNotIn(expected[:32].hex(), audit)

        empty = self.root / "empty.bin"
        empty.write_bytes(b"")
        status, headers, body = self.call_file(empty)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Content-Length"], "0")

    def test_size_limit_is_fixed(self):
        large = self.root / "large.bin"
        with large.open("wb") as handle:
            handle.seek(16 * 1024 * 1024)
            handle.write(b"x")
        status, _, body = self.call_file(large)
        self.assertEqual(status, 413)
        self.assertEqual(self.error_code(body), "FILE_TOO_LARGE")

    def test_drive_unc_ads_directory_and_missing_are_rejected(self):
        self.assertEqual(self.error_code(self.call_file(r"C:\Windows\win.ini")[2]), "PATH_NOT_ALLOWED")
        self.assertEqual(self.error_code(self.call_file(r"\\server\share\file.txt")[2]), "PATH_NOT_ALLOWED")
        ordinary = self.root / "ordinary.txt"
        ordinary.write_text("ordinary", encoding="utf-8")
        self.assertEqual(self.error_code(self.call_file(str(ordinary) + ":secret")[2]), "PATH_NOT_ALLOWED")
        self.assertEqual(self.error_code(self.call_file(self.root)[2]), "NOT_A_REGULAR_FILE")
        self.assertEqual(self.error_code(self.call_file(self.root / "missing.txt")[2]), "FILE_NOT_FOUND")

    def test_reparse_point_is_rejected(self):
        target = self.root / "outside.txt"
        target.write_text("outside", encoding="utf-8")
        link = self.root / "link.txt"
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError):
            link.write_text("placeholder", encoding="utf-8")
            with patch("jarvis_runner.file_export._is_reparse_point", return_value=True):
                status, _, body = self.call_file(link)
        else:
            status, _, body = self.call_file(link)
        self.assertEqual(status, 403)
        self.assertEqual(self.error_code(body), "PATH_NOT_ALLOWED")

    def test_auth_expiry_nonce_and_request_id_replay(self):
        source = self.root / "auth.txt"
        source.write_text("auth", encoding="utf-8")
        headers = self.signed_headers(str(source))
        bad = dict(headers)
        bad[FILE_AUTH_HEADERS["signature"]] = "0" * 64
        status, _, body = self.call_file(source, bad)
        self.assertEqual(status, 401)
        self.assertEqual(self.error_code(body), "AUTH_FAILED")

        now = datetime.now(timezone.utc)
        expired = self.signed_headers(str(source), issued_at=(now - timedelta(minutes=2)).isoformat(), expires_at=(now - timedelta(minutes=1)).isoformat())
        status, _, body = self.call_file(source, expired)
        self.assertEqual(status, 410)
        self.assertEqual(self.error_code(body), "REQUEST_EXPIRED")

        nonce_headers = self.signed_headers(str(source))
        self.assertEqual(self.call_file(source, nonce_headers)[0], 200)
        nonce_replay = self.signed_headers(str(source), nonce=nonce_headers[FILE_AUTH_HEADERS["nonce"]])
        status, _, body = self.call_file(source, nonce_replay)
        self.assertEqual(status, 409)
        self.assertEqual(self.error_code(body), "REPLAY_REJECTED")

        request_id = str(uuid.uuid4())
        first = self.signed_headers(str(source), request_id=request_id)
        self.assertEqual(self.call_file(source, first)[0], 200)
        request_replay = self.signed_headers(str(source), request_id=request_id)
        status, _, body = self.call_file(source, request_replay)
        self.assertEqual(status, 409)
        self.assertEqual(self.error_code(body), "REPLAY_REJECTED")

    def test_all_frozen_actions_still_work_over_task_endpoint(self):
        actions = [
            ("system.ping", {}),
            ("system.info", {}),
            ("system.status", {}),
            ("files.list_directory", {"path": str(self.root), "max_results": 5}),
            ("files.search", {"path": str(self.root), "query": "ordinary", "kind": "file"}),
            ("program.list", {}),
            ("program.run", {"program_id": "hello_jarvis"}),
        ]
        for action, arguments in actions:
            request = self.signed_task(action, arguments)
            status, _, body = self.call("/v1/task", json.dumps(request).encode("utf-8"), {"Content-Type": "application/json"})
            self.assertEqual(status, 200, action)
            self.assertEqual(json.loads(body.decode("utf-8"))["status"], "success", action)
