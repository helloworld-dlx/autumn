import http.client
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.auth import sign_request
from jarvis_runner.codex_worker import CodexWorkerService
from jarvis_runner.authority import AdmissionError, ExecutablePolicy
from jarvis_runner.config import RunnerConfig, validate_network_config
from jarvis_runner.errors import RunnerError
from jarvis_runner.models import JobResult
from jarvis_runner.network import TailscaleHTTPServer
from jarvis_runner.process_supervisor import ProcessSupervisor
from jarvis_runner.replay import ReplayCache


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r"D:\JarvisWorkspace\JarvisRunner\work")
        root = Path(self.temp.name); self.root = root; key_path = root / "key"; self.key = b"n" * 32; key_path.write_bytes(self.key)
        self.config = RunnerConfig(
            workspace_root=root.parent, runner_root=root, audit_log=root / "audit.jsonl", job_state_path=root / "state" / "jobs.json",
            read_root=Path("D:\\"), auth_key_path=key_path, listen_host="100.101.102.103", allowed_task_clients=("100.101.102.104",),
        )
        self.server = TailscaleHTTPServer(("127.0.0.1", 0), self.config, ReplayCache())
        self.server.client_ip_override = "100.101.102.104"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5); self.temp.cleanup()

    def signed(self, **changes):
        now = datetime.now(timezone.utc)
        request = {"protocol_version":"1.0", "request_id":str(uuid.uuid4()), "target_device":"windows-runner", "action":"system.ping", "arguments":{}, "issued_at":now.isoformat(), "expires_at":(now + timedelta(minutes=1)).isoformat(), "nonce":"network-nonce-abcdef", "key_id":"runner-local-v1"}
        request.update(changes); request["signature"] = sign_request(request, self.key); return request

    def call(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse(); status, server = response.status, response.getheader("Server")
        data = json.loads(response.read()); connection.close(); return status, data, server

    def test_health_and_source_restriction(self):
        status, body, server = self.call("GET", "/v1/health")
        self.assertEqual(status, 200); self.assertEqual(body, {"status":"ok", "protocol_version":"1.0", "runner":"jarvis-windows-runner"}); self.assertNotIn("Python", server)
        self.server.client_ip_override = "127.0.0.1"
        self.assertEqual(self.call("GET", "/v1/health")[0], 403)

    def test_task_auth_replay_and_source_precedes_auth(self):
        body = json.dumps(self.signed()).encode()
        self.assertEqual(self.call("POST", "/v1/task", body, {"Content-Type":"application/json"})[0], 200)
        self.assertEqual(self.call("POST", "/v1/task", body, {"Content-Type":"application/json"})[0], 409)
        bad_request = self.signed(); bad_request["signature"] = "0" * 64; bad = json.dumps(bad_request).encode()
        with patch("jarvis_runner.network.execute_signed_request") as execute:
            self.server.client_ip_override = "100.101.102.105"
            self.assertEqual(self.call("POST", "/v1/task", bad, {"Content-Type":"application/json"})[0], 403)
            execute.assert_not_called()
        self.server.client_ip_override = "100.101.102.104"
        self.assertEqual(self.call("POST", "/v1/task", bad, {"Content-Type":"application/json"})[0], 401)

    def test_http_rejections_and_no_directory_browsing(self):
        self.assertEqual(self.call("GET", "/unknown")[0], 404)
        self.assertEqual(self.call("PUT", "/v1/task")[0], 405)
        self.assertEqual(self.call("GET", "/v1/health?x=1")[0], 400)
        port = self.server.server_address[1]
        request = (
            "POST /v1/task HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: 65537\r\n"
            "Connection: close\r\n\r\n"
        ).encode()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.sendall(request)
            reply = connection.recv(4096)
        self.assertIn(b" 413 ", reply)
        self.assertEqual(self.call("POST", "/v1/task", b"\xff", {"Content-Type":"application/json"})[0], 400)

    def test_invalid_content_lengths_and_chunked_are_rejected(self):
        port = self.server.server_address[1]
        for headers in ("", "Content-Length: -1\r\n", "Content-Length: nope\r\n", "Transfer-Encoding: chunked\r\n"):
            raw = ("POST /v1/task HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n" + headers + "Connection: close\r\n\r\n{}").encode()
            with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
                connection.sendall(raw); reply = connection.recv(4096)
            self.assertIn(b" 400 ", reply)

    def test_expired_request_is_gone(self):
        now = datetime.now(timezone.utc)
        expired = self.signed(issued_at=(now-timedelta(minutes=2)).isoformat(), expires_at=(now-timedelta(minutes=1)).isoformat())
        body = json.dumps(expired).encode()
        self.assertEqual(self.call("POST", "/v1/task", body, {"Content-Type":"application/json"})[0], 410)

    def test_network_config_rejects_invalid_values(self):
        for host in ("0.0.0.0", "127.0.0.1", "192.168.1.1", "10.0.0.1", "172.16.0.1", "8.8.8.8", "::1", "host"):
            with self.assertRaises(ValueError): validate_network_config(replace(self.config, listen_host=host))
        with self.assertRaises(ValueError): validate_network_config(replace(self.config, allowed_task_clients=()))
        with self.assertRaises(ValueError): validate_network_config(replace(self.config, allowed_task_clients=("10.0.0.1",)))

    def test_job_api_auth_replay_submit_status_result_cancel_and_legacy_task(self):
        def job_call(route, action, arguments, *, request=None):
            request = request or self.signed(action=action, arguments=arguments, nonce=f"job-nonce-{uuid.uuid4().hex}")
            return self.call("POST", route, json.dumps(request).encode(), {"Content-Type": "application/json"}), request

        unsigned = self.signed(action="jobs.status", arguments={"job_id": str(uuid.uuid4())})
        unsigned["signature"] = "0" * 64
        self.assertEqual(job_call("/v1/jobs/status", "jobs.status", unsigned["arguments"], request=unsigned)[0][0], 401)

        archive = self.root / "input.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("one.txt", "one")
        submitted, request = job_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "operation": "archive.list", "arguments": {"archive_path": str(archive)},
        })
        self.assertEqual(submitted[0], 200, submitted[1])
        job_id = submitted[1]["output"]["job_id"]
        self.assertEqual(uuid.UUID(job_id).version, 4)
        self.assertIn(submitted[1]["output"]["status"], {"queued", "running", "succeeded"})
        self.assertEqual(job_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "operation": "archive.list", "arguments": {"archive_path": str(archive)},
        }, request=request)[0][0], 409)

        status, _ = job_call("/v1/jobs/status", "jobs.status", {"job_id": job_id})
        self.assertEqual(status[0], 200); self.assertEqual(status[1]["output"]["job_id"], job_id)

        queued = self.server.job_store.create("direct", "7zip")
        not_ready, _ = job_call("/v1/jobs/result", "jobs.result", {"job_id": queued.job_id})
        self.assertEqual((not_ready[0], not_ready[1]["error_code"]), (409, "NOT_READY"))
        cancelled, _ = job_call("/v1/jobs/cancel", "jobs.cancel", {"job_id": queued.job_id})
        self.assertEqual(cancelled[1]["output"]["status"], "cancelled")
        running = self.server.job_store.create("direct", "7zip")
        self.server.job_store.transition(running.job_id, "running")
        with patch.object(self.server.direct_worker.supervisor, "cancel") as cancel:
            delegated, _ = job_call("/v1/jobs/cancel", "jobs.cancel", {"job_id": running.job_id})
        cancel.assert_called_once_with(running.job_id)
        self.assertEqual(delegated[1]["output"]["job_id"], running.job_id)

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result, _ = job_call("/v1/jobs/result", "jobs.result", {"job_id": job_id})
            if result[0] == 200:
                break
            self.assertEqual(result[1]["error_code"], "NOT_READY")
            time.sleep(0.05)
        else:
            self.fail("job result was not ready")
        self.assertEqual(result[1]["output"]["result"]["status"], "succeeded")
        self.assertIn("stdout", result[1]["output"]["result"])

        source = self.root / "source"; source.mkdir(); (source / "probe.txt").write_text("job api smoke", encoding="utf-8")
        output_archive = self.root / "created.zip"
        created, _ = job_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "operation": "archive.create",
            "arguments": {"source_paths": [str(source)], "output_archive": str(output_archive)},
        })
        self.assertEqual(created[0], 200)
        create_job_id = created[1]["output"]["job_id"]
        self.assertEqual(uuid.UUID(create_job_id).version, 4)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            create_result, _ = job_call("/v1/jobs/result", "jobs.result", {"job_id": create_job_id})
            if create_result[0] == 200:
                break
            self.assertEqual(create_result[1]["error_code"], "NOT_READY")
            time.sleep(0.05)
        else:
            self.fail("archive.create result was not ready")
        self.assertEqual(create_result[1]["output"]["result"]["status"], "succeeded")
        self.assertTrue(output_archive.is_file())

        missing, _ = job_call("/v1/jobs/status", "jobs.status", {"job_id": str(uuid.uuid4())})
        self.assertEqual((missing[0], missing[1]["error_code"]), (404, "NOT_FOUND"))
        rejected, _ = job_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "operation": "archive.list",
            "arguments": {"archive_path": str(archive), "argv": ["x"]},
        })
        self.assertEqual(rejected[1]["error_code"], "REQUEST_INVALID")

        generic, _ = job_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "type": "process", "executable": "git", "arguments": ["--version"],
            "cwd": str(self.root), "timeout": 10, "write_scope": "none", "network_policy": "none",
        })
        self.assertEqual(generic[0], 200, generic[1])
        self.assertEqual((generic[1]["output"]["job_type"], generic[1]["output"]["backend"]), ("process", "git"))
        generic_job_id = generic[1]["output"]["job_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            generic_result, _ = job_call("/v1/jobs/result", "jobs.result", {"job_id": generic_job_id})
            if generic_result[0] == 200:
                break
            time.sleep(0.05)
        else:
            self.fail("generic process result was not ready")
        self.assertEqual(generic_result[1]["output"]["result"]["status"], "succeeded")

        python_denied, _ = job_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "type": "process", "executable": "python", "arguments": ["--version"],
            "cwd": str(self.root), "timeout": 10, "write_scope": "none", "network_policy": "none",
        })
        self.assertEqual((python_denied[0], python_denied[1]["error_code"]), (403, "AUTHORIZATION_REQUIRED"))
        raw_command, _ = job_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "type": "process", "executable": "git", "command": "git status",
            "cwd": str(self.root), "timeout": 10, "write_scope": "none", "network_policy": "none",
        })
        self.assertEqual(raw_command[1]["error_code"], "REQUEST_INVALID")
        legacy = self.call("POST", "/v1/task", json.dumps(self.signed()).encode(), {"Content-Type": "application/json"})
        self.assertEqual((legacy[0], legacy[1]["action"], legacy[1]["status"]), (200, "system.ping", "success"))

    def test_direct_process_streams_exit_code_empty_and_truncation_reach_jobs_result(self):
        helper = Path(__file__).parent / "helpers" / "worker_probe.py"
        preamble = ("-I", "-B", str(helper))
        policy = ExecutablePolicy(
            "worker_probe", Path(sys.executable), helper.parent,
            lambda argv: (
                len(argv) in (4, 5) and argv[:3] == preamble
                and argv[3] in {"success", "fail", "empty", "output"}
            ),
            test_only=True,
        )
        self.server.direct_worker.supervisor = ProcessSupervisor(
            self.server.job_store, self.config, catalog={"worker_probe": policy},
        )

        def job_call(route, action, arguments):
            request = self.signed(
                action=action, arguments=arguments,
                nonce=f"stream-nonce-{uuid.uuid4().hex}",
            )
            return self.call(
                "POST", route, json.dumps(request).encode(),
                {"Content-Type": "application/json"},
            )

        def run(arguments):
            submitted = job_call("/v1/jobs/submit", "jobs.submit", {
                "backend": "direct", "type": "process", "executable": "worker_probe",
                "arguments": [*preamble, *arguments], "cwd": str(helper.parent),
                "timeout": 10, "write_scope": "none", "network_policy": "none",
            })
            self.assertEqual(submitted[0], 200, submitted[1])
            job_id = submitted[1]["output"]["job_id"]
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                response = job_call("/v1/jobs/result", "jobs.result", {"job_id": job_id})
                if response[0] == 200:
                    return response[1]["output"]["result"]
                self.assertEqual(response[1]["error_code"], "NOT_READY")
                time.sleep(0.05)
            self.fail("fake process result was not ready")

        succeeded = run(["success"])
        self.assertEqual((succeeded["stdout"], succeeded["stderr"], succeeded["exit_code"]), ("hello\r\n", "", 0))
        self.assertEqual((succeeded["stdout_truncated"], succeeded["stderr_truncated"]), (False, False))

        failed = run(["fail"])
        self.assertEqual((failed["stdout"], failed["stderr"], failed["exit_code"]), ("", "failed\r\n", 7))

        empty = run(["empty"])
        self.assertEqual((empty["stdout"], empty["stderr"], empty["exit_code"]), ("", "", 0))

        truncated = run(["output", "9000"])
        self.assertLessEqual(len(truncated["stdout"].encode("utf-8")), 8192)
        self.assertLessEqual(len(truncated["stderr"].encode("utf-8")), 8192)
        self.assertEqual((truncated["stdout_truncated"], truncated["stderr_truncated"]), (True, True))

    def test_codex_authorization_api_and_submit_use_signed_subject_and_fake_process(self):
        class FakeCodexSupervisor:
            def __init__(self, store): self.store, self.started = store, []
            def start(self, job_id, request, completion_hook=None):
                self.started.append(request); self.store.transition(job_id, "running")
                output = Path(request.argv[request.argv.index("--output-last-message") + 1])
                output.write_text("fake Codex result", encoding="utf-8")
                result = JobResult("succeeded", "fake")
                if completion_hook is not None: result = completion_hook(job_id, result)
                self.store.transition(job_id, result.status, error_code=result.error_code, error_summary=result.summary)
                self.store.set_result(job_id, result)
            def cancel(self, job_id): del job_id

        fake = FakeCodexSupervisor(self.server.job_store)
        self.server.codex_worker = CodexWorkerService(
            self.config, self.server.authorizations, store=self.server.job_store,
            supervisor=fake,
        )

        def call_signed(route, action, arguments, *, key_id="runner-local-v1"):
            request = self.signed(action=action, arguments=arguments, key_id=key_id, nonce=f"codex-nonce-{uuid.uuid4().hex}")
            return self.call("POST", route, json.dumps(request).encode(), {"Content-Type": "application/json"})

        requested = call_signed("/v1/authorizations/request", "authorizations.request", {
            "task": "update a staged text file", "real_workspace": str(self.root),
        })
        self.assertEqual(requested[0], 200, requested[1])
        authorization_id = requested[1]["output"]["authorization_request_id"]
        self.assertEqual(requested[1]["output"]["status"], "pending")
        self.assertEqual(requested[1]["output"]["adapter"], "codex")
        self.assertEqual(requested[1]["output"]["authority"], "L3_WORKSPACE_WRITE")
        self.assertEqual(requested[1]["output"]["allowed_publish_effects"], ["CREATE", "MODIFY"])
        self.assertEqual(requested[1]["output"]["network_policy"], "none")
        self.assertEqual(call_signed("/v1/authorizations/approve", "authorizations.approve", {
            "authorization_request_id": authorization_id, "task": "attempt scope change",
        })[1]["error_code"], "REQUEST_INVALID")
        self.assertEqual(call_signed("/v1/jobs/submit", "jobs.submit", {
            "backend": "codex", "task": "update a staged text file", "real_workspace": str(self.root),
            "timeout": 10, "authorization_request_id": authorization_id,
        })[1]["error_code"], "AUTHORIZATION_NOT_APPROVED")
        approved = call_signed("/v1/authorizations/approve", "authorizations.approve", {"authorization_request_id": authorization_id})
        self.assertEqual((approved[0], approved[1]["output"]["status"]), (200, "approved"))
        submitted = call_signed("/v1/jobs/submit", "jobs.submit", {
            "backend": "codex", "task": "update a staged text file", "real_workspace": str(self.root),
            "timeout": 10, "authorization_request_id": authorization_id,
        })
        self.assertEqual((submitted[0], submitted[1]["output"]["backend"]), (200, "codex"))
        self.assertEqual(len(fake.started), 1)
        codex_result = call_signed("/v1/jobs/result", "jobs.result", {
            "job_id": submitted[1]["output"]["job_id"],
        })
        self.assertEqual(set(codex_result[1]["output"]["result"]), {
            "status", "summary", "exit_code", "error_code", "metadata",
        })
        self.assertEqual(call_signed("/v1/jobs/submit", "jobs.submit", {
            "backend": "codex", "task": "update a staged text file", "real_workspace": str(self.root),
            "timeout": 10, "authorization_request_id": authorization_id,
        })[1]["error_code"], "AUTHORIZATION_CONSUMED")

        mismatch = call_signed("/v1/authorizations/request", "authorizations.request", {
            "task": "fixed task", "real_workspace": str(self.root),
        })[1]["output"]["authorization_request_id"]
        call_signed("/v1/authorizations/approve", "authorizations.approve", {"authorization_request_id": mismatch})
        denied = call_signed("/v1/jobs/submit", "jobs.submit", {
            "backend": "codex", "task": "different task", "real_workspace": str(self.root),
            "timeout": 10, "authorization_request_id": mismatch,
        })
        self.assertEqual(denied[1]["error_code"], "AUTHORIZATION_SCOPE_MISMATCH")
        self.assertEqual(len(fake.started), 1)
        with self.assertRaises(RunnerError) as caught:
            self.server.authorizations.approve(mismatch, subject="another authenticated subject")
        self.assertEqual(caught.exception.code, "AUTHORIZATION_SUBJECT_MISMATCH")

        expired = call_signed("/v1/authorizations/request", "authorizations.request", {
            "task": "expired task", "real_workspace": str(self.root),
        })[1]["output"]["authorization_request_id"]
        self.server.authorizations._requests[expired] = replace(
            self.server.authorizations._requests[expired], expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        expired_submit = call_signed("/v1/jobs/submit", "jobs.submit", {
            "backend": "codex", "task": "expired task", "real_workspace": str(self.root),
            "timeout": 10, "authorization_request_id": expired,
        })
        self.assertEqual(expired_submit[1]["error_code"], "AUTHORIZATION_EXPIRED")
        self.assertEqual(len(fake.started), 1)

    def test_codex_start_rejection_retains_terminal_job_in_submit_response(self):
        class RejectingCodexSupervisor:
            def start(self, job_id, request, completion_hook=None):
                del job_id, request, completion_hook
                raise AdmissionError("PROCESS_POLICY_MISMATCH", "unsafe detail")
            def cancel(self, job_id): del job_id

        self.server.codex_worker = CodexWorkerService(
            self.config, self.server.authorizations, store=self.server.job_store,
            supervisor=RejectingCodexSupervisor(),
        )
        def call_signed(route, action, arguments):
            request = self.signed(action=action, arguments=arguments, nonce=f"rejection-nonce-{uuid.uuid4().hex}")
            return self.call("POST", route, json.dumps(request).encode(), {"Content-Type": "application/json"})

        requested = call_signed("/v1/authorizations/request", "authorizations.request", {
            "task": "update staged file", "real_workspace": str(self.root),
        })
        authorization_id = requested[1]["output"]["authorization_request_id"]
        call_signed("/v1/authorizations/approve", "authorizations.approve", {"authorization_request_id": authorization_id})
        status, body, _ = call_signed("/v1/jobs/submit", "jobs.submit", {
            "backend": "codex", "task": "update staged file", "real_workspace": str(self.root),
            "timeout": 10, "authorization_request_id": authorization_id,
        })
        self.assertEqual((status, body["status"], body["error_code"]), (400, "rejected", "CODEX_START_REJECTED"))
        self.assertEqual((body["output"]["status"], body["output"]["error_code"]), ("cancelled", "CODEX_START_REJECTED"))
        self.assertTrue(body["output"]["job_id"])

    def test_worker_emergency_stop_gates_submits_cancels_active_jobs_and_resumes(self):
        def signed_call(route, action, arguments):
            request = self.signed(
                action=action, arguments=arguments,
                nonce=f"worker-control-{uuid.uuid4().hex}",
            )
            return self.call(
                "POST", route, json.dumps(request).encode(),
                {"Content-Type": "application/json"},
            )

        status = signed_call("/v1/workers/status", "workers.status", {})
        self.assertEqual((status[0], status[1]["output"]), (200, {"workers_paused": False}))

        requested = signed_call("/v1/authorizations/request", "authorizations.request", {
            "task": "approved but paused task", "real_workspace": str(self.root),
        })
        authorization_id = requested[1]["output"]["authorization_request_id"]
        signed_call("/v1/authorizations/approve", "authorizations.approve", {
            "authorization_request_id": authorization_id,
        })

        active = []
        for backend, state in (("git", "queued"), ("git", "running"), ("codex", "queued"), ("codex", "running")):
            record = self.server.job_store.create("agent" if backend == "codex" else "process", backend)
            if state == "running":
                self.server.job_store.transition(record.job_id, "running")
            active.append(record.job_id)

        def cancel(job_id):
            record = self.server.job_store.get(job_id)
            if record is not None and record.status not in {"succeeded", "failed", "cancelled", "timed_out", "interrupted_by_restart"}:
                self.server.job_store.transition(job_id, "cancelled", error_code="CANCELLED", error_summary="job cancelled")
                self.server.job_store.set_result(job_id, JobResult("cancelled", "job cancelled", error_code="CANCELLED"))

        class FakeCodexWorker:
            def cancel(self, job_id):
                cancel(job_id)

        self.server.codex_worker = FakeCodexWorker()
        with patch.object(self.server.direct_worker.supervisor, "cancel", side_effect=cancel):
            paused = signed_call("/v1/workers/pause", "workers.pause", {})
        self.assertEqual(paused[0], 200, paused[1])
        self.assertEqual(paused[1]["output"], {
            "workers_paused": True, "stopped": 0, "cancelled": 4, "failed": 0,
        })
        self.assertTrue(all(self.server.job_store.get(job_id).status == "cancelled" for job_id in active))

        before = len(self.server.job_store.list_records())
        direct = signed_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "type": "process", "executable": "git", "arguments": ["--version"],
            "cwd": str(self.root), "timeout": 10, "write_scope": "none", "network_policy": "none",
        })
        self.assertEqual((direct[0], direct[1]["status"], direct[1]["error_code"]), (409, "rejected", "WORKERS_PAUSED"))
        self.assertEqual(len(self.server.job_store.list_records()), before)

        codex = signed_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "codex", "task": "approved but paused task", "real_workspace": str(self.root),
            "timeout": 10, "authorization_request_id": authorization_id,
        })
        self.assertEqual((codex[0], codex[1]["error_code"]), (409, "WORKERS_PAUSED"))
        self.assertEqual(self.server.authorizations._requests[authorization_id].status, "approved")
        self.assertEqual(len(self.server.job_store.list_records()), before)

        job_id = active[0]
        self.assertEqual(signed_call("/v1/jobs/status", "jobs.status", {"job_id": job_id})[0], 200)
        self.assertEqual(signed_call("/v1/jobs/result", "jobs.result", {"job_id": job_id})[0], 200)
        cancelled = signed_call("/v1/jobs/cancel", "jobs.cancel", {"job_id": job_id})
        self.assertEqual((cancelled[0], cancelled[1]["output"]["status"]), (200, "cancelled"))
        repeated = signed_call("/v1/workers/pause", "workers.pause", {})
        self.assertEqual(repeated[1]["output"], {
            "workers_paused": True, "stopped": 0, "cancelled": 0, "failed": 0,
        })

        self.assertEqual(signed_call("/v1/workers/resume", "workers.resume", {})[1]["output"], {"workers_paused": False})
        self.assertEqual(signed_call("/v1/workers/resume", "workers.resume", {})[1]["output"], {"workers_paused": False})
        resumed = signed_call("/v1/jobs/submit", "jobs.submit", {
            "backend": "direct", "type": "process", "executable": "git", "arguments": ["--version"],
            "cwd": str(self.root), "timeout": 10, "write_scope": "none", "network_policy": "none",
        })
        self.assertEqual(resumed[0], 200, resumed[1])

    def test_worker_pause_remains_active_when_one_cancel_fails(self):
        record = self.server.job_store.create("process", "git")
        request = self.signed(
            action="workers.pause", arguments={},
            nonce=f"worker-control-{uuid.uuid4().hex}",
        )
        with patch.object(self.server.direct_worker.supervisor, "cancel", side_effect=ValueError("fake cancel failure")):
            status, body, _ = self.call(
                "POST", "/v1/workers/pause", json.dumps(request).encode(),
                {"Content-Type": "application/json"},
            )
        self.assertEqual(status, 200, body)
        self.assertEqual(body["output"], {
            "workers_paused": True, "stopped": 0, "cancelled": 0, "failed": 1,
        })
        self.assertTrue(self.server.worker_control.workers_paused)
        self.assertEqual(self.server.job_store.get(record.job_id).status, "queued")
