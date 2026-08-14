from __future__ import annotations

import json
import ntpath
import ipaddress
from dataclasses import dataclass
from pathlib import Path


PRODUCTION_WORKSPACE_ROOT = Path(r"D:\JarvisWorkspace").resolve(strict=False)
DEFAULT_WORKSPACE_ROOT = PRODUCTION_WORKSPACE_ROOT
DEFAULT_RUNNER_ROOT = PRODUCTION_WORKSPACE_ROOT / "JarvisRunner"
PRODUCTION_READ_ROOT = Path("D:\\").resolve(strict=False)
PRODUCTION_SECRET_ROOT = Path(r"D:\JarvisWorkspace\JarvisSecrets")
PRODUCTION_AUTH_KEY_PATH = PRODUCTION_SECRET_ROOT / "runner_auth.key"
TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")
DEFAULT_LISTEN_HOST = "100.101.102.103"
DEFAULT_ALLOWED_TASK_CLIENTS = ("100.101.102.104",)
DEFAULT_LISTEN_PORT = 27891
DEFAULT_MAXIMUM_HTTP_BODY_BYTES = 65536
DEFAULT_AUDIT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_AUDIT_BACKUP_COUNT = 3
AUDIT_MAX_BYTES_CONFIG_MINIMUM = 4096
AUDIT_MAX_BYTES_HARD_LIMIT = 50 * 1024 * 1024
AUDIT_BACKUP_COUNT_HARD_LIMIT = 10
DEFAULT_JOB_TERMINAL_TTL_SECONDS = 24 * 60 * 60
DEFAULT_JOB_MAX_RECORDS = 1000
JOB_TERMINAL_TTL_HARD_LIMIT_SECONDS = 7 * 24 * 60 * 60
JOB_MAX_RECORDS_HARD_LIMIT = 10000
DEFAULT_PROCESS_TIMEOUT_MIN_SECONDS = 1
DEFAULT_PROCESS_TIMEOUT_MAX_SECONDS = 60
PROCESS_TIMEOUT_HARD_MAX_SECONDS = 300
AGENT_STAGING_DIRECTORY_NAME = "AgentStaging"

LIST_DEFAULTS = {"max_results": 50, "max_scanned_entries": 2000, "timeout_ms": 2000}
LIST_HARD_LIMITS = {"max_results": 100, "max_scanned_entries": 5000, "timeout_ms": 5000}
SEARCH_DEFAULTS = {"max_results": 50, "max_scanned_entries": 20000, "max_depth": 8, "timeout_ms": 3000}
SEARCH_HARD_LIMITS = {"max_results": 100, "max_scanned_entries": 100000, "max_depth": 32, "timeout_ms": 10000}


@dataclass(frozen=True)
class RunnerConfig:
    runner_version: str = "0.1.0"
    workspace_root: Path = DEFAULT_WORKSPACE_ROOT
    runner_root: Path = DEFAULT_RUNNER_ROOT
    audit_log: Path = DEFAULT_RUNNER_ROOT / "logs" / "audit.jsonl"
    audit_max_bytes: int = DEFAULT_AUDIT_MAX_BYTES
    audit_backup_count: int = DEFAULT_AUDIT_BACKUP_COUNT
    job_state_path: Path = DEFAULT_RUNNER_ROOT / "state" / "jobs.json"
    job_terminal_ttl_seconds: int = DEFAULT_JOB_TERMINAL_TTL_SECONDS
    job_max_records: int = DEFAULT_JOB_MAX_RECORDS
    process_timeout_min_seconds: int = DEFAULT_PROCESS_TIMEOUT_MIN_SECONDS
    process_timeout_max_seconds: int = DEFAULT_PROCESS_TIMEOUT_MAX_SECONDS
    maximum_argument_string_length: int = 1000
    maximum_output_string_length: int = 10000
    maximum_argument_depth: int = 8
    maximum_argument_nodes: int = 1000
    maximum_argument_json_length: int = 20000
    maximum_output_json_length: int = 20000
    maximum_output_nodes: int = 1000
    read_root: Path = PRODUCTION_READ_ROOT
    list_directory_max_results: int = 50
    list_directory_max_scanned_entries: int = 2000
    list_directory_timeout_ms: int = 2000
    search_max_results: int = 50
    search_max_scanned_entries: int = 20000
    search_max_depth: int = 8
    search_timeout_ms: int = 3000
    auth_key_path: Path = PRODUCTION_AUTH_KEY_PATH
    listen_host: str = DEFAULT_LISTEN_HOST
    listen_port: int = DEFAULT_LISTEN_PORT
    allowed_task_clients: tuple[str, ...] = DEFAULT_ALLOWED_TASK_CLIENTS
    maximum_http_body_bytes: int = DEFAULT_MAXIMUM_HTTP_BODY_BYTES


def _tailscale_ipv4(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an exact Tailscale IPv4 address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an exact Tailscale IPv4 address") from error
    if address.version != 4 or address not in TAILSCALE_NETWORK:
        raise ValueError(f"{field_name} must be an exact Tailscale IPv4 address")
    return str(address)


def validate_network_config(config: RunnerConfig) -> None:
    _tailscale_ipv4(config.listen_host, "listen_host")
    if not isinstance(config.listen_port, int) or isinstance(config.listen_port, bool) or not 1024 <= config.listen_port <= 65535:
        raise ValueError("listen_port must be between 1024 and 65535")
    if not isinstance(config.allowed_task_clients, tuple) or not config.allowed_task_clients:
        raise ValueError("allowed_task_clients must be a non-empty list")
    for client in config.allowed_task_clients:
        _tailscale_ipv4(client, "allowed_task_clients entry")
    if not isinstance(config.maximum_http_body_bytes, int) or isinstance(config.maximum_http_body_bytes, bool) or not 1 <= config.maximum_http_body_bytes <= 65536:
        raise ValueError("maximum_http_body_bytes must be between 1 and 65536")


def _resolved(path_value: object, field_name: str) -> Path:
    if not isinstance(path_value, str) or not path_value:
        raise ValueError(f"{field_name} must be a non-empty path string")
    return Path(path_value).resolve(strict=False)


def _within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _fixed_read_root(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("read_root must be a non-empty absolute drive path")
    raw = value.replace("/", "\\")
    if raw.startswith("\\\\") or raw.startswith("\\\\?\\") or raw.startswith("\\\\.\\"):
        raise ValueError("read_root must not be UNC or device namespace")
    drive, tail = ntpath.splitdrive(raw)
    if drive.casefold() != "d:" or not tail.startswith("\\") or ":" in raw[2:]:
        raise ValueError("read_root must exactly be D:\\")
    if any(part == ".." for part in tail.split("\\")):
        raise ValueError("read_root must not contain path traversal")
    normalized = ntpath.normpath(raw)
    if normalized.casefold() != "d:\\".casefold():
        raise ValueError("read_root must exactly be D:\\")
    return Path(normalized).resolve(strict=False)


def _fixed_auth_key_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("auth_key_path must be a non-empty absolute path")
    raw = value.replace("/", "\\")
    if raw.startswith("\\\\") or raw.startswith("\\\\?\\") or raw.startswith("\\\\.\\"):
        raise ValueError("auth_key_path must not be UNC or device namespace")
    drive, tail = ntpath.splitdrive(raw)
    if drive.casefold() != "d:" or not tail.startswith("\\") or ":" in raw[2:] or any(part == ".." for part in tail.split("\\")):
        raise ValueError("auth_key_path is outside approved secret root")
    normalized = Path(ntpath.normpath(raw)).absolute()
    try:
        normalized.relative_to(PRODUCTION_SECRET_ROOT.absolute())
    except ValueError as error:
        raise ValueError("auth_key_path is outside approved secret root") from error
    return normalized


def load_config(runner_root: Path | None = None) -> RunnerConfig:
    base = (runner_root or DEFAULT_RUNNER_ROOT).resolve(strict=False)
    config_path = base / "config" / "runner.json"
    values: dict[str, object] = {}
    if config_path.is_file():
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("runner.json must contain a JSON object")
        values = loaded

    workspace_root = _resolved(values.get("workspace_root", str(PRODUCTION_WORKSPACE_ROOT)), "workspace_root")
    if workspace_root != PRODUCTION_WORKSPACE_ROOT:
        raise ValueError("workspace_root must exactly match the fixed production workspace root")
    resolved_runner_root = _resolved(values.get("runner_root", str(base)), "runner_root")
    audit_log = _resolved(values.get("audit_log", str(resolved_runner_root / "logs" / "audit.jsonl")), "audit_log")
    if not _within(resolved_runner_root, workspace_root):
        raise ValueError("runner_root must be inside workspace_root")
    if not _within(audit_log, resolved_runner_root):
        raise ValueError("audit_log must be inside runner_root")

    def positive_int(name: str, default: int) -> int:
        value = values.get(name, default)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    def bounded_int(name: str, default: int, hard_limit: int) -> int:
        value = positive_int(name, default)
        if value > hard_limit:
            raise ValueError(f"{name} exceeds its code hard limit")
        return value

    version = values.get("runner_version", "0.1.0")
    if not isinstance(version, str) or not version:
        raise ValueError("runner_version must be a non-empty string")
    maximum_argument_string_length = positive_int("maximum_argument_string_length", 1000)
    maximum_output_string_length = positive_int("maximum_output_string_length", 10000)
    maximum_output_json_length = positive_int("maximum_output_json_length", 20000)
    maximum_output_nodes = positive_int("maximum_output_nodes", 1000)
    if maximum_output_string_length < maximum_argument_string_length:
        raise ValueError("output budgets cannot contain the base response")
    audit_max_bytes = bounded_int("audit_max_bytes", DEFAULT_AUDIT_MAX_BYTES, AUDIT_MAX_BYTES_HARD_LIMIT)
    if audit_max_bytes < AUDIT_MAX_BYTES_CONFIG_MINIMUM:
        raise ValueError(f"audit_max_bytes must be at least {AUDIT_MAX_BYTES_CONFIG_MINIMUM} bytes")
    audit_backup_count = bounded_int("audit_backup_count", DEFAULT_AUDIT_BACKUP_COUNT, AUDIT_BACKUP_COUNT_HARD_LIMIT)
    job_terminal_ttl_seconds = bounded_int(
        "job_terminal_ttl_seconds", DEFAULT_JOB_TERMINAL_TTL_SECONDS, JOB_TERMINAL_TTL_HARD_LIMIT_SECONDS
    )
    job_max_records = bounded_int("job_max_records", DEFAULT_JOB_MAX_RECORDS, JOB_MAX_RECORDS_HARD_LIMIT)
    process_timeout_min_seconds = bounded_int("process_timeout_min_seconds", DEFAULT_PROCESS_TIMEOUT_MIN_SECONDS, PROCESS_TIMEOUT_HARD_MAX_SECONDS)
    process_timeout_max_seconds = bounded_int("process_timeout_max_seconds", DEFAULT_PROCESS_TIMEOUT_MAX_SECONDS, PROCESS_TIMEOUT_HARD_MAX_SECONDS)
    if process_timeout_min_seconds > process_timeout_max_seconds:
        raise ValueError("process timeout minimum exceeds maximum")
    candidate = RunnerConfig(
        runner_version=version,
        workspace_root=workspace_root,
        runner_root=resolved_runner_root,
        audit_log=audit_log,
        audit_max_bytes=audit_max_bytes,
        audit_backup_count=audit_backup_count,
        job_state_path=resolved_runner_root / "state" / "jobs.json",
        job_terminal_ttl_seconds=job_terminal_ttl_seconds,
        job_max_records=job_max_records,
        process_timeout_min_seconds=process_timeout_min_seconds,
        process_timeout_max_seconds=process_timeout_max_seconds,
        maximum_argument_string_length=maximum_argument_string_length,
        maximum_output_string_length=maximum_output_string_length,
        maximum_argument_depth=positive_int("maximum_argument_depth", 8),
        maximum_argument_nodes=positive_int("maximum_argument_nodes", 1000),
        maximum_argument_json_length=positive_int("maximum_argument_json_length", 20000),
        maximum_output_json_length=maximum_output_json_length,
        maximum_output_nodes=maximum_output_nodes,
        read_root=_fixed_read_root(values.get("read_root", str(PRODUCTION_READ_ROOT))),
        list_directory_max_results=bounded_int("list_directory_max_results", LIST_DEFAULTS["max_results"], LIST_HARD_LIMITS["max_results"]),
        list_directory_max_scanned_entries=bounded_int("list_directory_max_scanned_entries", LIST_DEFAULTS["max_scanned_entries"], LIST_HARD_LIMITS["max_scanned_entries"]),
        list_directory_timeout_ms=bounded_int("list_directory_timeout_ms", LIST_DEFAULTS["timeout_ms"], LIST_HARD_LIMITS["timeout_ms"]),
        search_max_results=bounded_int("search_max_results", SEARCH_DEFAULTS["max_results"], SEARCH_HARD_LIMITS["max_results"]),
        search_max_scanned_entries=bounded_int("search_max_scanned_entries", SEARCH_DEFAULTS["max_scanned_entries"], SEARCH_HARD_LIMITS["max_scanned_entries"]),
        search_max_depth=bounded_int("search_max_depth", SEARCH_DEFAULTS["max_depth"], SEARCH_HARD_LIMITS["max_depth"]),
        search_timeout_ms=bounded_int("search_timeout_ms", SEARCH_DEFAULTS["timeout_ms"], SEARCH_HARD_LIMITS["timeout_ms"]),
        auth_key_path=_fixed_auth_key_path(values.get("auth_key_path", str(PRODUCTION_AUTH_KEY_PATH))),
        listen_host=_tailscale_ipv4(values.get("listen_host", DEFAULT_LISTEN_HOST), "listen_host"),
        listen_port=values.get("listen_port", DEFAULT_LISTEN_PORT),
        allowed_task_clients=tuple(values["allowed_task_clients"]) if isinstance(values.get("allowed_task_clients", DEFAULT_ALLOWED_TASK_CLIENTS), list) else DEFAULT_ALLOWED_TASK_CLIENTS,
        maximum_http_body_bytes=values.get("maximum_http_body_bytes", DEFAULT_MAXIMUM_HTTP_BODY_BYTES),
    )
    validate_network_config(candidate)
    from .security import validate_output
    try:
        from .files import worst_case_base_response
        validate_output(worst_case_base_response(candidate), candidate)
    except ValueError as error:
        raise ValueError("output budgets cannot contain the base response") from error
    return candidate
