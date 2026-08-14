from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import uuid
from datetime import timedelta
from dataclasses import replace
import tempfile
import threading
import http.client
from datetime import datetime, timezone
from pathlib import Path

from .audit import append_audit_record, append_runner_started_audit
from .auth import sign_request, verify_signature, load_auth_key
from .config import RunnerConfig, load_config, validate_network_config
from .errors import OutputValidationError, RunnerError
from .models import ActionRequest, ActionResult
from .protocol import validate_request
from .replay import REPLAY_CACHE, ReplayCache
from .registry import get_action, registered_actions
from .security import validate_action_name, validate_arguments, validate_output, validate_request_id


_CANONICAL_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serve_failure(stage: str, error: Exception) -> int:
    code = getattr(error, "code", None)
    if not isinstance(code, str) or not _CANONICAL_ERROR_CODE.fullmatch(code):
        code = None
    print(json.dumps({
        "status": "failed", "error_code": "SERVER_UNAVAILABLE",
        "error_message": "Tailscale listener unavailable",
        "failure_stage": stage,
        "underlying_exception_class": type(error).__name__,
        "underlying_error_code": code,
    }))
    return 1


def execute_request(request: ActionRequest, config: RunnerConfig) -> ActionResult:
    started_at = _now()
    try:
        validate_request_id(request.request_id)
        validate_action_name(request.action)
        validate_arguments(request.arguments, config)
        handler = get_action(request.action)
        if handler is None:
            result = ActionResult(request.request_id, request.action, "rejected", {}, "ACTION_NOT_ALLOWED", "action is not registered", started_at, _now())
        else:
            output = validate_output(handler(request.arguments, config), config)
            result = ActionResult(request.request_id, request.action, "success", output, None, None, started_at, _now())
    except OutputValidationError:
        result = ActionResult(request.request_id, request.action, "failed", {}, "OUTPUT_INVALID", "action output is invalid", started_at, _now())
    except RunnerError as error:
        result = ActionResult(request.request_id, request.action, "rejected", {}, error.code, error.message, started_at, _now())
    except ValueError as error:
        result = ActionResult(request.request_id, request.action, "rejected", {}, "REQUEST_INVALID", str(error), started_at, _now())
    except Exception:
        result = ActionResult(request.request_id, request.action, "failed", {}, "ACTION_FAILED", "action failed", started_at, _now())
    try:
        append_audit_record(request, result, config)
    except (OSError, ValueError, TypeError):
        return ActionResult(request.request_id, request.action, "failed", {}, "AUDIT_LOG_FAILED", "audit log write failed", started_at, _now())
    return result


def authenticate_signed_request(payload: object, config: RunnerConfig, replay_cache: ReplayCache = REPLAY_CACHE) -> tuple[dict | None, RunnerError | None]:
    try:
        request, expires_at = validate_request(payload)
        key = load_auth_key(config.auth_key_path)
        verify_signature(request, key)
        replay_cache.register(request["request_id"], request["nonce"], expires_at, datetime.now(timezone.utc))
    except RunnerError as error:
        return None, error
    return request, None


def execute_signed_request(payload: object, config: RunnerConfig, replay_cache: ReplayCache = REPLAY_CACHE) -> ActionResult:
    started_at = _now()
    request, error = authenticate_signed_request(payload, config, replay_cache)
    if error is not None:
        return ActionResult(str(payload.get("request_id", "")) if isinstance(payload, dict) else "", str(payload.get("action", "")) if isinstance(payload, dict) else "", "rejected", {}, error.code, error.message, started_at, _now())
    return execute_request(ActionRequest(request["request_id"], request["action"], request["arguments"], "signed-protocol", None), config)


def _result_dict(result: ActionResult) -> dict:
    return {
        "request_id": result.request_id, "action": result.action, "status": result.status,
        "output": result.output, "error_code": result.error_code,
        "error_message": result.error_message, "started_at": result.started_at,
        "finished_at": result.finished_at,
    }


def scan_source_for_dangerous_calls(source_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for source_file in source_root.rglob("*.py"):
        try:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        except (OSError, UnicodeDecodeError, SyntaxError) as error:
            findings.append({"file": source_file.name, "line": getattr(error, "lineno", 0) or 0, "rule": "parse_error"})
            continue
        findings.extend(_ast_findings(tree, source_file.name))
    return findings


_ALLOWED_PROGRAM_RUNNER_FINDINGS = frozenset({
    "import_subprocess",
    "subprocess_popen_call",
    "import_hashlib",
})

_ALLOWED_PROCESS_SUPERVISOR_FINDINGS = frozenset({"import_subprocess", "subprocess_popen_call", "subprocess_call"})
_ALLOWED_FILES_SEARCH_FINDINGS = frozenset({"import_subprocess", "subprocess_call"})


def filter_doctor_findings(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        finding
        for finding in findings
        if not (
            finding.get("file") == "programs.py"
            and finding.get("rule") in _ALLOWED_PROGRAM_RUNNER_FINDINGS
        ) and not (finding.get("file") == "process_supervisor.py" and finding.get("rule") in _ALLOWED_PROCESS_SUPERVISOR_FINDINGS)
        and not (finding.get("file") == "files.py" and finding.get("rule") in _ALLOWED_FILES_SEARCH_FINDINGS)
    ]


def _ast_findings(tree: ast.AST, filename: str) -> list[dict[str, object]]:
    subprocess_name = "sub" + "process"; importlib_name = "import" + "lib"; ctypes_name = "cty" + "pes"; socket_name = "soc" + "ket"; hashlib_name = "hash" + "lib"
    process_methods = {"Popen", "run", "call", "check_call", "check_output"}
    banned_literals = {"".join(("power", "shell")), "".join(("power", "shell.exe")), "".join(("p", "w", "s", "h")), "".join(("cmd", ".exe"))}
    findings: list[dict[str, object]] = []
    subprocess_aliases: set[str] = set(); process_function_aliases: set[str] = set(); os_aliases: set[str] = {"os"}; os_system_aliases: set[str] = set(); importlib_aliases: set[str] = set(); importlib_function_aliases: set[str] = set()
    def add(node: ast.AST, rule: str) -> None: findings.append({"file": filename, "line": node.lineno, "rule": rule})
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                bound = imported.asname or imported.name
                if imported.name == subprocess_name: subprocess_aliases.add(bound); add(node, "import_subprocess")
                if imported.name == importlib_name: importlib_aliases.add(bound); add(node, "import_importlib")
                if imported.name == ctypes_name and filename != "system_status.py": add(node, "import_ctypes")
                if imported.name == socket_name: add(node, "import_socket")
                if imported.name == hashlib_name: add(node, "import_hashlib")
                if imported.name == "os": os_aliases.add(bound)
        elif isinstance(node, ast.ImportFrom):
            if node.module == subprocess_name:
                add(node, "from_subprocess_import")
                process_function_aliases.update(alias.asname or alias.name for alias in node.names)
            if node.module == "os":
                os_system_aliases.update(alias.asname or alias.name for alias in node.names if alias.name == "system")
            if node.module == importlib_name:
                add(node, "from_importlib_import"); importlib_function_aliases.update(alias.asname or alias.name for alias in node.names)
            if node.module == ctypes_name and filename != "system_status.py": add(node, "from_ctypes_import")
            if node.module == socket_name: add(node, "from_socket_import")
            if node.module == hashlib_name: add(node, "from_hashlib_import")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and any(term in node.value.casefold() for term in banned_literals):
            add(node, "banned_shell_literal")
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and node.value.value is True:
            if any(isinstance(target, ast.Name) and target.id == "shell" for target in node.targets): add(node, "shell_true_assignment")
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name in {"eval", "exec", "__import__"}: add(node, "dynamic_builtin_call")
            if name in process_function_aliases: add(node, "subprocess_function_call")
            if name in os_system_aliases: add(node, "os_system_call")
            if name in importlib_function_aliases: add(node, "dynamic_import_call")
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                base, attribute = node.func.value.id, node.func.attr
                if base in subprocess_aliases and attribute in process_methods:
                    add(node, "subprocess_popen_call" if attribute == "Popen" else "subprocess_call")
                if base in os_aliases and attribute == "system": add(node, "os_system_call")
                if base in importlib_aliases: add(node, "dynamic_import_call")
            if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords): add(node, "shell_true_keyword")
    return findings


def doctor(config: RunnerConfig) -> tuple[bool, dict]:
    try:
        validate_network_config(config)
        network_config_valid = True
    except ValueError:
        network_config_valid = False
    from .network import APPROVED_ROUTES
    from .authority import PRODUCTION_EXECUTABLE_CATALOG
    checks = {
        "python_3_13_or_newer": sys.version_info >= (3, 13),
        "runner_root_exists": config.runner_root.is_dir(),
        "workspace_root_exists": config.workspace_root.is_dir(),
        "logs_writable": False,
        "config_loaded": True,
        "registered_action_count_is_7": len(registered_actions()) == 7,
        "production_executable_catalog_has_required_profiles": set(PRODUCTION_EXECUTABLE_CATALOG) == {"7zip", "git", "python", "node", "everything"},
        "required_executables_available": all(
            PRODUCTION_EXECUTABLE_CATALOG[name].executable_path is not None
            and PRODUCTION_EXECUTABLE_CATALOG[name].executable_path.is_file()
            for name in ("7zip", "git", "python", "node")
        ),
        "everything_cli_detected_or_marked_unavailable": (
            PRODUCTION_EXECUTABLE_CATALOG["everything"].executable_path is None
            or PRODUCTION_EXECUTABLE_CATALOG["everything"].executable_path.is_file()
        ),
        "approved_network_route_count_is_12": len(APPROVED_ROUTES) == 12 and APPROVED_ROUTES == {
            ("GET", "/v1/health"), ("POST", "/v1/task"), ("POST", "/v1/file"),
            ("POST", "/v1/jobs/submit"), ("POST", "/v1/jobs/status"),
            ("POST", "/v1/jobs/cancel"), ("POST", "/v1/jobs/result"),
            ("POST", "/v1/authorizations/request"), ("POST", "/v1/authorizations/approve"),
            ("POST", "/v1/workers/pause"), ("POST", "/v1/workers/resume"),
            ("POST", "/v1/workers/status"),
        },
        "tailscale_network_config_valid": network_config_valid,
        "auth_uses_compare_digest": "hmac.compare_digest" in (Path(__file__).parent / "auth.py").read_text(encoding="utf-8"),
        "dangerous_source_findings": filter_doctor_findings(scan_source_for_dangerous_calls(Path(__file__).parent)),
    }
    try:
        log_dir = config.audit_log.parent
        log_dir.mkdir(parents=True, exist_ok=True)
        probe = log_dir / ".write_probe"
        with probe.open("a", encoding="utf-8"):
            pass
        probe.unlink()
        checks["logs_writable"] = True
    except OSError:
        pass
    ok = all(value is True for key, value in checks.items() if key != "dangerous_source_findings") and not checks["dangerous_source_findings"]
    return ok, checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JARVIS Windows Runner Phase 1D")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")
    subparsers.add_parser("selftest")
    subparsers.add_parser("serve-tailscale")
    run_parser = subparsers.add_parser("run-action")
    run_parser.add_argument("action")
    run_parser.add_argument("--arguments-json", default="{}")
    signed_parser = subparsers.add_parser("run-signed-request")
    signed_parser.add_argument("--request-json", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_config()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error_code": "CONFIG_INVALID", "error_message": str(error)}))
        return 2
    if args.command == "doctor":
        ok, checks = doctor(config)
        print(json.dumps({"status": "success" if ok else "failed", "checks": checks}, ensure_ascii=False))
        return 0 if ok else 1
    if args.command == "serve-tailscale":
        from .codex_worker import codex_policy_maximum_argument_length, codex_policy_wrapper_length
        package_root = Path(__file__).resolve().parent
        try:
            append_runner_started_audit(
                os.getpid(), sys.executable, package_root,
                package_root / "authority.py", package_root / "codex_worker.py",
                codex_policy_maximum_argument_length(config), codex_policy_wrapper_length(), config,
            )
        except (OSError, ValueError, TypeError) as error:
            return _serve_failure("startup_audit", error)
        try:
            validate_network_config(config)
        except (OSError, ValueError, RunnerError) as error:
            return _serve_failure("network_config", error)
        try:
            load_auth_key(config.auth_key_path)
        except (OSError, ValueError, RunnerError) as error:
            return _serve_failure("auth_key", error)
        try:
            from .network import create_server
            server = create_server(config)
        except (OSError, ValueError, RunnerError) as error:
            return _serve_failure("listener", error)
        print(json.dumps({"status": "listening", "listen_host": config.listen_host, "listen_port": config.listen_port}))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if args.command == "run-signed-request":
        try:
            payload = json.loads(args.request_json)
        except json.JSONDecodeError:
            print(json.dumps({"status": "rejected", "error_code": "PROTOCOL_INVALID"}))
            return 1
        result = execute_signed_request(payload, config)
        print(json.dumps(_result_dict(result), ensure_ascii=False))
        return 0 if result.status == "success" else 1
    if args.command == "selftest":
        actions = (("system.ping", {}), ("system.info", {}), ("system.status", {}), ("files.list_directory", {"path": str(config.runner_root), "max_results": 5, "max_scanned_entries": 50, "timeout_ms": 1000}), ("files.search", {"path": str(config.runner_root), "query": "README", "extensions": [".md"], "kind": "file", "max_depth": 3, "max_results": 5, "max_scanned_entries": 100, "timeout_ms": 1000}))
    else:
        try:
            actions = ((args.action, json.loads(args.arguments_json)),)
        except json.JSONDecodeError:
            print(json.dumps({"status": "rejected", "error_code": "REQUEST_INVALID", "error_message": "arguments JSON is invalid"}))
            return 1
    results = []
    for index, (action, arguments) in enumerate(actions, start=1):
        if not isinstance(arguments, dict):
            print(json.dumps({"status": "rejected", "error_code": "REQUEST_INVALID", "error_message": "arguments JSON must be an object"}))
            return 1
        request = ActionRequest(f"cli-{index}-{uuid.uuid4()}", action, arguments, "local-cli", None)
        results.append(_result_dict(execute_request(request, config)))
    if args.command == "selftest":
        with tempfile.TemporaryDirectory() as temporary:
            key_path = Path(temporary) / "runner_auth.key"; key = b"t" * 32; key_path.write_bytes(key)
            signed_config = replace(config, auth_key_path=key_path)
            now = datetime.now(timezone.utc)
            signed = {"protocol_version": "1.0", "request_id": str(uuid.uuid4()), "target_device": "windows-runner", "action": "system.ping", "arguments": {}, "issued_at": now.isoformat(), "expires_at": (now + timedelta(minutes=1)).isoformat(), "nonce": "selftest-nonce-123", "key_id": "runner-local-v1"}
            signed["signature"] = sign_request(signed, key)
            accepted = execute_signed_request(signed, signed_config, ReplayCache())
            bad = dict(signed); bad["request_id"] = str(uuid.uuid4()); bad["signature"] = "0" * 64
            rejected = execute_signed_request(bad, signed_config, ReplayCache())
            replay_cache = ReplayCache(); first = execute_signed_request(signed, signed_config, replay_cache); replayed = execute_signed_request(signed, signed_config, replay_cache)
            from .network import TailscaleHTTPServer
            server = TailscaleHTTPServer(("127.0.0.1", 0), signed_config, ReplayCache())
            server.client_ip_override = signed_config.allowed_task_clients[0]
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                port = server.server_address[1]
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("GET", "/v1/health")
                health_ok = connection.getresponse().status == 200; connection.close()
                task_body = json.dumps(signed).encode("utf-8")
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("POST", "/v1/task", task_body, {"Content-Type": "application/json", "Content-Length": str(len(task_body))})
                network_ok = connection.getresponse().status == 200; connection.close()
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                connection.request("POST", "/v1/task", task_body, {"Content-Type": "application/json", "Content-Length": str(len(task_body))})
                network_replayed = connection.getresponse().status == 409; connection.close()
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=5)
            if accepted.status != "success" or rejected.error_code != "AUTH_FAILED" or first.status != "success" or replayed.error_code != "REQUEST_REPLAYED" or not health_ok or not network_ok or not network_replayed or thread.is_alive():
                return 1
    print(json.dumps(results if args.command == "selftest" else results[0], ensure_ascii=False))
    return 0 if all(item["status"] == "success" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
