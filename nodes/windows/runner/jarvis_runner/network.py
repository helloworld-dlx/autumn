"""Minimal Tailscale-only HTTP adapter; importing this module never starts a listener."""
from __future__ import annotations

import json
import ipaddress
import ntpath
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .audit import append_file_export_audit, append_job_audit_event
from .authority import AdmissionError
from .cli import _result_dict, authenticate_signed_request, execute_signed_request
from .config import RunnerConfig, TAILSCALE_NETWORK, validate_network_config
from .errors import RunnerError
from .file_export import iter_file_chunks, prepare_file
from .direct_worker import DirectProcessWorkerService, process_job_spec_from_wire
from .codex_worker import CodexStartRejectedError, CodexTaskRequest, CodexWorkerService
from .jobs import JobStateError, JobStore
from .models import JOB_TERMINAL_STATUSES, JobRecord, JobResult
from .replay import REPLAY_CACHE, ReplayCache
from .task_authorization import PendingAuthorization, TaskAuthorizationStore
from .worker_control import WorkerControlState

HEALTH_RESPONSE = {"status": "ok", "protocol_version": "1.0", "runner": "jarvis-windows-runner"}
APPROVED_ROUTES = frozenset({
    ("GET", "/v1/health"), ("POST", "/v1/task"), ("POST", "/v1/file"),
    ("POST", "/v1/jobs/submit"), ("POST", "/v1/jobs/status"),
    ("POST", "/v1/jobs/cancel"), ("POST", "/v1/jobs/result"), ("POST", "/v1/jobs/list"),
    ("POST", "/v1/authorizations/request"), ("POST", "/v1/authorizations/approve"),
    ("POST", "/v1/authorizations/list"),
    ("POST", "/v1/workers/pause"), ("POST", "/v1/workers/resume"),
    ("POST", "/v1/workers/status"),
})
_JOB_ROUTE_ACTIONS = {
    "/v1/jobs/submit": "jobs.submit",
    "/v1/jobs/status": "jobs.status",
    "/v1/jobs/cancel": "jobs.cancel",
    "/v1/jobs/result": "jobs.result",
    "/v1/jobs/list": "jobs.list",
}
_AUTHORIZATION_ROUTE_ACTIONS = {
    "/v1/authorizations/request": "authorizations.request",
    "/v1/authorizations/approve": "authorizations.approve",
    "/v1/authorizations/list": "authorizations.list",
}
_WORKER_CONTROL_ROUTE_ACTIONS = {
    "/v1/workers/pause": "workers.pause",
    "/v1/workers/resume": "workers.resume",
    "/v1/workers/status": "workers.status",
}
FILE_AUTH_HEADERS = {
    "request_id": "X-Autumn-Request-Id",
    "issued_at": "X-Autumn-Issued-At",
    "expires_at": "X-Autumn-Expires-At",
    "nonce": "X-Autumn-Nonce",
    "key_id": "X-Autumn-Key-Id",
    "signature": "X-Autumn-Signature",
}


def _status_for_result(error_code: str | None) -> int:
    return {"AUTH_FAILED": 401, "REQUEST_REPLAYED": 409, "REQUEST_EXPIRED": 410,
            "AUTH_KEY_UNAVAILABLE": 503}.get(error_code, 200)


class TailscaleHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], config: RunnerConfig, replay_cache: ReplayCache = REPLAY_CACHE):
        self.config = config
        self.replay_cache = replay_cache
        self.client_ip_override: str | None = None  # test-only hook; never set by production startup
        self.job_store = JobStore(config, audit_callback=append_job_audit_event)
        self.job_store.load()
        self.worker_control = WorkerControlState(config)
        self.direct_worker = DirectProcessWorkerService(config, store=self.job_store)
        self.authorizations = TaskAuthorizationStore(config)
        self.codex_worker: CodexWorkerService | None = None
        super().__init__(address, TailscaleRequestHandler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


class TailscaleRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "jarvis-runner"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:
        return

    @property
    def _config(self) -> RunnerConfig:
        return self.server.config  # type: ignore[attr-defined]

    def _client_ip(self) -> str:
        override = self.server.client_ip_override  # type: ignore[attr-defined]
        return override if override is not None else self.client_address[0]

    def _codex_worker(self) -> CodexWorkerService:
        worker = self.server.codex_worker  # type: ignore[attr-defined]
        if worker is None:
            worker = CodexWorkerService(
                self._config, self.server.authorizations, store=self.server.job_store,  # type: ignore[attr-defined]
            )
            self.server.codex_worker = worker  # type: ignore[attr-defined]
        return worker

    def _send_json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    def _error(self, status: int, code: str) -> None:
        self._send_json(status, {"status": "rejected", "error_code": code, "error_message": "request rejected"})

    def _path(self) -> str | None:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            self._error(400, "QUERY_NOT_ALLOWED")
            return None
        return parsed.path

    def do_GET(self) -> None:
        path = self._path()
        if path is None:
            return
        if path == "/v1/task":
            self._method_not_allowed()
            return
        if path != "/v1/health":
            self._error(404, "NOT_FOUND")
            return
        try:
            allowed = ipaddress.ip_address(self._client_ip()) in TAILSCALE_NETWORK
        except ValueError:
            allowed = False
        if not allowed:
            self._error(403, "SOURCE_NOT_ALLOWED")
            return
        self._send_json(200, HEALTH_RESPONSE)

    def do_POST(self) -> None:
        path = self._path()
        if path is None:
            return
        if path == "/v1/health":
            self._method_not_allowed()
            return
        if path == "/v1/file":
            self._file_export()
            return
        if path in _JOB_ROUTE_ACTIONS:
            self._job_api(path)
            return
        if path in _AUTHORIZATION_ROUTE_ACTIONS:
            self._authorization_api(path)
            return
        if path in _WORKER_CONTROL_ROUTE_ACTIONS:
            self._worker_control_api(path)
            return
        if path != "/v1/task":
            self._error(404, "NOT_FOUND")
            return
        if self._client_ip() not in self._config.allowed_task_clients:
            self._error(403, "SOURCE_NOT_ALLOWED")
            return
        if self.headers.get("Transfer-Encoding"):
            self._error(400, "TRANSFER_ENCODING_NOT_ALLOWED")
            return
        content_type = self.headers.get("Content-Type", "")
        content_type_parts = [part.strip() for part in content_type.split(";")]
        if content_type_parts[0].casefold() != "application/json" or any(part and part.casefold() != "charset=utf-8" for part in content_type_parts[1:]):
            self._error(400, "CONTENT_TYPE_INVALID")
            return
        length_header = self.headers.get("Content-Length")
        try:
            if length_header is None or not length_header.isascii() or not length_header.isdecimal():
                raise ValueError
            length = int(length_header)
            if length <= 0:
                raise ValueError
        except ValueError:
            self._error(400, "CONTENT_LENGTH_INVALID")
            return
        if length > self._config.maximum_http_body_bytes:
            self._error(413, "BODY_TOO_LARGE")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "JSON_INVALID")
            return
        if not isinstance(payload, dict):
            self._error(400, "JSON_OBJECT_REQUIRED")
            return
        result = execute_signed_request(payload, self._config, self.server.replay_cache)  # type: ignore[attr-defined]
        self._send_json(_status_for_result(result.error_code), _result_dict(result))

    @staticmethod
    def _job_status(record: JobRecord) -> dict:
        return {
            "job_id": record.job_id, "status": record.status,
            "created_at": record.created_at, "updated_at": record.updated_at,
            "started_at": record.started_at, "finished_at": record.finished_at,
            "job_type": record.job_type, "backend": record.backend,
            "error_code": record.error_code,
        }

    @staticmethod
    def _job_result(result: JobResult, *, include_process_streams: bool = False) -> dict:
        """Return the bounded public result; Direct streams were bounded before storage."""
        output = {
            "status": result.status, "summary": result.summary, "exit_code": result.exit_code,
            "error_code": result.error_code, "metadata": result.metadata,
        }
        if include_process_streams:
            metadata = result.metadata or {}
            output.update({
                "stdout": result.stdout, "stderr": result.stderr,
                "stdout_truncated": metadata.get("stdout_truncated", False),
                "stderr_truncated": metadata.get("stderr_truncated", False),
            })
        return output

    @staticmethod
    def _job_error_status(code: str) -> int:
        return {
            "AUTH_FAILED": 401, "REQUEST_REPLAYED": 409, "REQUEST_EXPIRED": 410,
            "AUTH_KEY_UNAVAILABLE": 503, "NOT_FOUND": 404, "NOT_READY": 409,
            "OUTPUT_ALREADY_EXISTS": 409, "PATH_NOT_ALLOWED": 403,
            "OPERATION_NOT_ALLOWED": 403,
            "EXECUTABLE_NOT_ALLOWED": 403, "ARGUMENTS_NOT_ALLOWED": 403,
            "CWD_NOT_ALLOWED": 403, "PROCESS_POLICY_MISMATCH": 403,
            "PROCESS_TIMEOUT_NOT_ALLOWED": 403, "NOT_YET_AUTHORIZED": 403,
            "AUTHORIZATION_REQUIRED": 403, "DELETE_HARD_DENY": 403, "DENY": 403,
            "AUTHORIZATION_NOT_FOUND": 404, "AUTHORIZATION_EXPIRED": 410,
            "AUTHORIZATION_NOT_APPROVED": 403, "AUTHORIZATION_CONSUMED": 409,
            "AUTHORIZATION_SUBJECT_MISMATCH": 403, "AUTHORIZATION_SCOPE_MISMATCH": 403,
            "WORKERS_PAUSED": 409, "WORKER_STATE_PERSIST_FAILED": 503,
            "EXECUTABLE_UNAVAILABLE": 503,
        }.get(code, 400)

    def _job_response(self, request_id: str, status: str, output: dict | None = None, error_code: str | None = None) -> None:
        self._send_json(self._job_error_status(error_code) if error_code else 200, {
            "request_id": request_id, "status": status, "output": output or {},
            "error_code": error_code, "error_message": None if error_code is None else "request rejected",
        })

    def _job_api(self, path: str) -> None:
        if self._client_ip() not in self._config.allowed_task_clients:
            self._error(403, "SOURCE_NOT_ALLOWED")
            return
        body_ok, payload = self._read_json_body()
        if not body_ok:
            return
        request_id = str(payload.get("request_id", "")) if isinstance(payload, dict) else ""
        request, auth_error = authenticate_signed_request(payload, self._config, self.server.replay_cache)  # type: ignore[attr-defined]
        if auth_error is not None:
            self._job_response(request_id, "rejected", error_code=auth_error.code)
            return
        assert request is not None
        if request["action"] != _JOB_ROUTE_ACTIONS[path]:
            self._job_response(request["request_id"], "rejected", error_code="REQUEST_INVALID")
            return
        try:
            if path == "/v1/jobs/submit":
                output = self._job_submit(request["arguments"], subject=request["key_id"])
            elif path == "/v1/jobs/status":
                output = self._job_status_for(request["arguments"])
            elif path == "/v1/jobs/cancel":
                output = self._job_cancel(request["arguments"])
            elif path == "/v1/jobs/list":
                output = self._job_list(request["arguments"])
            else:
                output = self._job_result_for(request["arguments"])
        except RunnerError as error:
            output = self._job_status(error.job) if isinstance(error, CodexStartRejectedError) else None
            self._job_response(request["request_id"], "rejected", output=output, error_code=error.code)
            return
        except AdmissionError as error:
            self._job_response(request["request_id"], "rejected", error_code=error.code)
            return
        except (JobStateError, ValueError):
            self._job_response(request["request_id"], "failed", error_code="INTERNAL_ERROR")
            return
        self._job_response(request["request_id"], "success", output)

    @staticmethod
    def _authorization_summary(request: PendingAuthorization) -> dict:
        return {
            "authorization_request_id": request.authorization_request_id,
            "status": request.status,
            "adapter": request.adapter,
            "authority": request.authority_level.name,
            "allowed_publish_effects": list(request.allowed_publish_effects),
            "network_policy": request.network_policy,
            "task": request.task_summary,
            "real_workspace": str(request.real_workspace),
            "expires_at": request.expires_at.isoformat(),
        }

    @staticmethod
    def _authorization_activity_summary(request: PendingAuthorization) -> dict:
        # Companion activity is intentionally narrower than the worker API: no full workspace path.
        workspace = ntpath.basename(str(request.real_workspace).rstrip("\\/")) or "workspace"
        return {
            "authorization_request_id": request.authorization_request_id,
            "status": request.status,
            "authority": request.authority_level.name,
            "task": request.task_summary,
            "workspace": workspace,
            "expires_at": request.expires_at.isoformat(),
        }

    def _authorization_api(self, path: str) -> None:
        if self._client_ip() not in self._config.allowed_task_clients:
            self._error(403, "SOURCE_NOT_ALLOWED")
            return
        body_ok, payload = self._read_json_body()
        if not body_ok:
            return
        request_id = str(payload.get("request_id", "")) if isinstance(payload, dict) else ""
        request, auth_error = authenticate_signed_request(payload, self._config, self.server.replay_cache)  # type: ignore[attr-defined]
        if auth_error is not None:
            self._job_response(request_id, "rejected", error_code=auth_error.code)
            return
        assert request is not None
        if request["action"] != _AUTHORIZATION_ROUTE_ACTIONS[path]:
            self._job_response(request["request_id"], "rejected", error_code="REQUEST_INVALID")
            return
        try:
            arguments = request["arguments"]
            if path == "/v1/authorizations/request":
                if not isinstance(arguments, dict) or set(arguments) != {"task", "real_workspace"}:
                    raise RunnerError("REQUEST_INVALID", "authorization request is invalid")
                authorization = self.server.authorizations.create_request(  # type: ignore[attr-defined]
                    subject=request["key_id"], adapter="codex", task_summary=arguments["task"],
                    real_workspace=arguments["real_workspace"], network_policy="none",
                )
            elif path == "/v1/authorizations/list":
                if arguments != {}:
                    raise RunnerError("REQUEST_INVALID", "authorization list request is invalid")
                pending = self.server.authorizations.list_pending()  # type: ignore[attr-defined]
                self._job_response(request["request_id"], "success", {
                    "authorizations": [self._authorization_activity_summary(item) for item in pending]
                })
                return
            else:
                if not isinstance(arguments, dict) or set(arguments) != {"authorization_request_id"}:
                    raise RunnerError("REQUEST_INVALID", "authorization approval is invalid")
                authorization = self.server.authorizations.approve(  # type: ignore[attr-defined]
                    arguments["authorization_request_id"], subject=request["key_id"],
                )
        except RunnerError as error:
            self._job_response(request["request_id"], "rejected", error_code=error.code)
            return
        self._job_response(request["request_id"], "success", self._authorization_summary(authorization))

    def _worker_control_api(self, path: str) -> None:
        if self._client_ip() not in self._config.allowed_task_clients:
            self._error(403, "SOURCE_NOT_ALLOWED")
            return
        body_ok, payload = self._read_json_body()
        if not body_ok:
            return
        request_id = str(payload.get("request_id", "")) if isinstance(payload, dict) else ""
        request, auth_error = authenticate_signed_request(payload, self._config, self.server.replay_cache)  # type: ignore[attr-defined]
        if auth_error is not None:
            self._job_response(request_id, "rejected", error_code=auth_error.code)
            return
        assert request is not None
        if request["action"] != _WORKER_CONTROL_ROUTE_ACTIONS[path] or request["arguments"] != {}:
            self._job_response(request["request_id"], "rejected", error_code="REQUEST_INVALID")
            return
        try:
            if path == "/v1/workers/pause":
                output = self._pause_workers()
            elif path == "/v1/workers/resume":
                self.server.worker_control.resume()  # type: ignore[attr-defined]
                output = {"workers_paused": False}
            else:
                output = {"workers_paused": self.server.worker_control.workers_paused}  # type: ignore[attr-defined]
        except RunnerError as error:
            self._job_response(request["request_id"], "failed", error_code=error.code)
            return
        self._job_response(request["request_id"], "success", output)

    def _pause_workers(self) -> dict:
        self.server.worker_control.pause()  # type: ignore[attr-defined]
        snapshot = tuple(
            record for record in self.server.job_store.list_records()  # type: ignore[attr-defined]
            if record.status not in JOB_TERMINAL_STATUSES
        )
        stopped = cancelled = failed = 0
        for record in snapshot:
            current = self.server.job_store.get(record.job_id)  # type: ignore[attr-defined]
            if current is None or current.status in JOB_TERMINAL_STATUSES:
                stopped += 1
                continue
            try:
                self._cancel_worker_job(current)
                cancelled += 1
            except Exception:
                failed += 1
        return {
            "workers_paused": True, "stopped": stopped,
            "cancelled": cancelled, "failed": failed,
        }

    def _job_submit(self, arguments: object, *, subject: str) -> dict:
        with self.server.worker_control.admit_submission():  # type: ignore[attr-defined]
            if not isinstance(arguments, dict):
                raise RunnerError("REQUEST_INVALID", "job submit request is invalid")
            if set(arguments) == {"backend", "task", "real_workspace", "timeout", "authorization_request_id"} and arguments.get("backend") == "codex":
                job = self._codex_worker().submit(CodexTaskRequest(
                    subject=subject, task=arguments["task"],
                    real_workspace=arguments["real_workspace"], timeout=arguments["timeout"],
                    authorization_request_id=arguments["authorization_request_id"],
                ))
            elif set(arguments) == {"backend", "operation", "arguments"} and arguments.get("backend") == "direct":
                job = self.server.direct_worker.submit_direct_job(arguments["operation"], arguments["arguments"])  # type: ignore[attr-defined]
            elif set(arguments) == {"backend", "type", "executable", "arguments", "cwd", "timeout", "write_scope", "network_policy"} and arguments.get("backend") == "direct":
                wire_spec = {key: value for key, value in arguments.items() if key != "backend"}
                spec = process_job_spec_from_wire(wire_spec, self._config)
                job = self.server.direct_worker.submit_process_job(spec)  # type: ignore[attr-defined]
            else:
                raise RunnerError("REQUEST_INVALID", "job submit request is invalid")
        current = self.server.job_store.get(job.job_id)  # type: ignore[attr-defined]
        return self._job_status(current or job)

    def _job_list(self, arguments: object) -> dict:
        if not isinstance(arguments, dict) or set(arguments) != {"limit"}:
            raise RunnerError("REQUEST_INVALID", "job list request is invalid")
        limit = arguments.get("limit")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise RunnerError("REQUEST_INVALID", "job list limit is invalid")
        records = sorted(
            self.server.job_store.list_records(),  # type: ignore[attr-defined]
            key=lambda record: record.updated_at, reverse=True,
        )[:limit]
        return {"jobs": [self._job_status(record) for record in records]}

    def _job_record(self, arguments: object) -> JobRecord:
        if not isinstance(arguments, dict) or set(arguments) != {"job_id"} or not isinstance(arguments["job_id"], str):
            raise RunnerError("NOT_FOUND", "job was not found")
        record = self.server.job_store.get(arguments["job_id"])  # type: ignore[attr-defined]
        if record is None:
            raise RunnerError("NOT_FOUND", "job was not found")
        return record

    def _job_status_for(self, arguments: object) -> dict:
        return self._job_status(self._job_record(arguments))

    def _job_cancel(self, arguments: object) -> dict:
        record = self._job_record(arguments)
        if record.status not in JOB_TERMINAL_STATUSES:
            self._cancel_worker_job(record)
        current = self.server.job_store.get(record.job_id)  # type: ignore[attr-defined]
        return self._job_status(current or record)

    def _cancel_worker_job(self, record: JobRecord) -> None:
        if record.backend == "codex":
            self._codex_worker().cancel(record.job_id)
        else:
            self.server.direct_worker.supervisor.cancel(record.job_id)  # type: ignore[attr-defined]

    def _job_result_for(self, arguments: object) -> dict:
        record = self._job_record(arguments)
        if record.status not in JOB_TERMINAL_STATUSES or record.result is None:
            raise RunnerError("NOT_READY", "job result is not ready")
        return {
            "job_id": record.job_id,
            "result": self._job_result(record.result, include_process_streams=record.backend != "codex"),
        }

    def _read_json_body(self) -> tuple[bool, object]:
        if self.headers.get("Transfer-Encoding"):
            self._error(400, "TRANSFER_ENCODING_NOT_ALLOWED")
            return False, None
        content_type = self.headers.get("Content-Type", "")
        content_type_parts = [part.strip() for part in content_type.split(";")]
        if content_type_parts[0].casefold() != "application/json" or any(part and part.casefold() != "charset=utf-8" for part in content_type_parts[1:]):
            self._error(400, "CONTENT_TYPE_INVALID")
            return False, None
        length_header = self.headers.get("Content-Length")
        try:
            if length_header is None or not length_header.isascii() or not length_header.isdecimal():
                raise ValueError
            length = int(length_header)
            if length <= 0:
                raise ValueError
        except ValueError:
            self._error(400, "CONTENT_LENGTH_INVALID")
            return False, None
        if length > self._config.maximum_http_body_bytes:
            self._error(413, "BODY_TOO_LARGE")
            return False, None
        try:
            return True, json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "JSON_INVALID")
            return False, None

    def _file_signed_payload(self, path: str) -> dict:
        values = {name: self.headers.get(header) for name, header in FILE_AUTH_HEADERS.items()}
        if any(not isinstance(value, str) or not value for value in values.values()):
            raise RunnerError("AUTH_FAILED", "authentication failed")
        return {
            "protocol_version": "1.0",
            "request_id": values["request_id"],
            "target_device": "windows-runner",
            "action": "file.export",
            "arguments": {"path": path},
            "issued_at": values["issued_at"],
            "expires_at": values["expires_at"],
            "nonce": values["nonce"],
            "key_id": values["key_id"],
            "signature": values["signature"],
        }

    def _audit_file(self, request_id: str, status: str, file_size: int | None, started: float, error_code: str | None) -> None:
        try:
            append_file_export_audit(request_id, status, file_size, int((time.monotonic() - started) * 1000), error_code, self._config)
        except (OSError, ValueError, TypeError):
            return

    def _file_error_status(self, code: str) -> int:
        return {
            "AUTH_FAILED": 401,
            "REQUEST_REPLAYED": 409,
            "REPLAY_REJECTED": 409,
            "REQUEST_EXPIRED": 410,
            "FILE_NOT_FOUND": 404,
            "PATH_NOT_ALLOWED": 403,
            "FILE_TOO_LARGE": 413,
            "FILE_CHANGED": 409,
            "NOT_A_REGULAR_FILE": 400,
            "READ_FAILED": 500,
            "AUTH_KEY_UNAVAILABLE": 503,
        }.get(code, 400)

    def _file_export(self) -> None:
        started = time.monotonic()
        if self._client_ip() not in self._config.allowed_task_clients:
            self._error(403, "SOURCE_NOT_ALLOWED")
            return
        body_ok, payload = self._read_json_body()
        if not body_ok:
            return
        if not isinstance(payload, dict) or set(payload) != {"path"} or not isinstance(payload["path"], str):
            self._error(400, "REQUEST_INVALID")
            return
        path = payload["path"]
        try:
            signed = self._file_signed_payload(path)
            request, auth_error = authenticate_signed_request(signed, self._config, self.server.replay_cache)  # type: ignore[attr-defined]
            if auth_error is not None:
                code = "REPLAY_REJECTED" if auth_error.code == "REQUEST_REPLAYED" else auth_error.code
                self._audit_file(self.headers.get(FILE_AUTH_HEADERS["request_id"], ""), "failed", None, started, code)
                self._error(self._file_error_status(code), code)
                return
            assert request is not None
            prepared = prepare_file(request["arguments"]["path"], self._config)
        except RunnerError as error:
            code = "REPLAY_REJECTED" if error.code == "REQUEST_REPLAYED" else error.code
            self._audit_file(self.headers.get(FILE_AUTH_HEADERS["request_id"], ""), "failed", getattr(error, "file_size", None), started, code)
            self._error(self._file_error_status(code), code)
            return

        filename = ntpath.basename(str(prepared.path))
        safe_filename = "".join(character if 32 <= ord(character) < 127 else "_" for character in filename) or "file"
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(prepared.size))
            self.send_header("Connection", "close")
            self.send_header("X-Autumn-Filename", safe_filename)
            self.send_header("X-Autumn-Size", str(prepared.size))
            self.end_headers()
            for chunk in iter_file_chunks(prepared):
                self.wfile.write(chunk)
            self.close_connection = True
            stream_error_code = None
        except RunnerError as error:
            stream_error_code = error.code
            self.close_connection = True
        except OSError:
            stream_error_code = "READ_FAILED"
            self.close_connection = True
        finally:
            try:
                prepared.handle.close()
            except OSError:
                pass
        self._audit_file(request["request_id"], "success" if stream_error_code is None else "failed", prepared.size, started, stream_error_code)

    def do_PUT(self) -> None: self._method_not_allowed()
    def do_DELETE(self) -> None: self._method_not_allowed()
    def do_PATCH(self) -> None: self._method_not_allowed()
    def do_HEAD(self) -> None: self._method_not_allowed()
    def do_OPTIONS(self) -> None: self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        self._error(405, "METHOD_NOT_ALLOWED")

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        if code == 501:
            self._error(405, "METHOD_NOT_ALLOWED")
            return
        self._error(code, "REQUEST_INVALID")


def create_server(config: RunnerConfig, replay_cache: ReplayCache = REPLAY_CACHE) -> TailscaleHTTPServer:
    validate_network_config(config)
    return TailscaleHTTPServer((config.listen_host, config.listen_port), config, replay_cache)
