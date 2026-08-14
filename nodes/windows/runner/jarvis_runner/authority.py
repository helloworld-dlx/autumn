"""Runner-owned admission for internal Direct Worker process specifications."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable, Mapping

from .config import RunnerConfig
from .models import ProcessJobSpec


class AuthorityLevel(IntEnum):
    L0_QUERY = 0
    L1_READ_OPEN = 1
    L2_CREATE_PROCESS = 2
    L3_WORKSPACE_WRITE = 3
    L4_EXTERNAL_EFFECT = 4
    L5_SYSTEM_ADMIN = 5


class AdmissionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProcessRequest:
    """Untrusted-shaped input. requested_authority is informational only."""
    executable_id: str
    argv: tuple[str, ...] | list[str]
    cwd: Path
    timeout_seconds: int
    write_scope: str = "none"
    network_policy: str = "none"
    operation_type: str = "process"
    requested_authority: AuthorityLevel | None = None


@dataclass(frozen=True)
class ExecutablePolicy:
    executable_id: str
    executable_path: Path | None
    cwd: Path
    argument_validator: Callable[[tuple[str, ...]], bool]
    write_scope: str = "none"
    network_policy: str = "none"
    operation_type: str = "process"
    test_only: bool = False
    allowed_operation_types: frozenset[str] | None = None
    policy_class: str = "generic_process"
    minimum_authority: AuthorityLevel = AuthorityLevel.L2_CREATE_PROCESS
    capabilities: frozenset[str] = frozenset()
    authority_classifier: Callable[[tuple[str, ...]], AuthorityLevel] | None = None
    argument_transformer: Callable[[tuple[str, ...]], tuple[str, ...]] | None = None
    allow_cwd_descendants: bool = False
    maximum_argument_string_length: int | None = None


@dataclass(frozen=True)
class ApprovedProcessSpec:
    executable_id: str
    executable_path: Path
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int
    write_scope: str
    network_policy: str
    required_authority: AuthorityLevel


SEVEN_ZIP_EXECUTABLE_PATH = Path(r"C:\Program Files\7-Zip\7z.exe")
GIT_EXECUTABLE_PATH = Path(r"D:\Program Files\Git\cmd\git.exe")
PYTHON_EXECUTABLE_PATH = Path(r"C:\Users\丁励行\AppData\Local\Programs\Python\Python313\python.exe")
NODE_EXECUTABLE_PATH = Path(r"C:\Program Files\nodejs\node.exe")
EVERYTHING_EXECUTABLE_CANDIDATES = (
    Path(r"D:\JarvisWorkspace\JarvisRunner\tools\everything\es.exe"),
    Path(r"C:\Program Files\Everything\es.exe"),
    Path(r"C:\Program Files (x86)\Everything\es.exe"),
    Path(r"C:\Users\丁励行\AppData\Local\Everything\es.exe"),
)
EVERYTHING_EXECUTABLE_PATH = next((path for path in EVERYTHING_EXECUTABLE_CANDIDATES if path.is_file()), None)


def _seven_zip_arguments(argv: tuple[str, ...]) -> bool:
    if len(argv) == 4 and argv[:3] == ("l", "-ba", "-slt"):
        return argv[3].casefold().startswith("d:\\") and argv[3].casefold().endswith(".zip")
    if len(argv) >= 5 and argv[:3] == ("a", "-tzip", "-bd"):
        return all(value.casefold().startswith("d:\\") for value in argv[3:]) and argv[3].casefold().endswith(".zip")
    return False


def _seven_zip_authority(argv: tuple[str, ...]) -> AuthorityLevel:
    return AuthorityLevel.L1_READ_OPEN if argv[0] == "l" else AuthorityLevel.L2_CREATE_PROCESS


def _nonempty_arguments(argv: tuple[str, ...]) -> bool:
    return bool(argv)


def _everything_arguments(argv: tuple[str, ...]) -> bool:
    # Everything is only invoked by files.search, which constructs its fixed
    # read-only argv.  The Direct Worker must not expose ES syntax or flags.
    return False


_GIT_READ_ONLY = frozenset({"status", "diff", "log", "show", "rev-parse"})
_GIT_WORKSPACE_WRITE = frozenset({"add", "commit", "checkout", "switch", "restore", "reset"})
_GIT_NETWORK = frozenset({"push", "pull", "fetch", "clone"})
_GIT_DESTRUCTIVE_FLAGS = frozenset({"--hard", "--merge", "--keep"})
_GIT_EXTERNAL_EXEC_FLAGS = frozenset({"--ext-diff", "--textconv"})


def _git_arguments(argv: tuple[str, ...]) -> bool:
    return bool(argv) and (argv[0] == "--version" or not argv[0].startswith("-"))


def _git_authority(argv: tuple[str, ...]) -> AuthorityLevel:
    command = argv[0].casefold()
    lowered = {value.casefold() for value in argv[1:]}
    if command == "--version":
        return AuthorityLevel.L1_READ_OPEN
    if command == "clean" or (command == "reset" and lowered & _GIT_DESTRUCTIVE_FLAGS):
        raise AdmissionError("DENY", "destructive Git operation is denied")
    if lowered & _GIT_EXTERNAL_EXEC_FLAGS:
        raise AdmissionError("DENY", "external Git helper execution is denied")
    if any(value == "--output" or value.startswith("--output=") for value in lowered):
        raise AdmissionError("DENY", "Git output file creation is denied")
    if command in _GIT_READ_ONLY:
        return AuthorityLevel.L1_READ_OPEN
    if command in _GIT_WORKSPACE_WRITE:
        return AuthorityLevel.L3_WORKSPACE_WRITE
    if command in _GIT_NETWORK:
        return AuthorityLevel.L4_EXTERNAL_EFFECT
    raise AdmissionError("OPERATION_NOT_ALLOWED", "Git operation is not allowed")


def _safe_git_arguments(argv: tuple[str, ...]) -> tuple[str, ...]:
    command, rest = argv[0], argv[1:]
    if command.casefold() in {"diff", "log", "show"}:
        return ("--no-pager", command, "--no-ext-diff", "--no-textconv", *rest)
    return ("--no-pager", *argv)


# Declarative Runner-owned production catalog. Program differences stay in small policies.
PRODUCTION_EXECUTABLE_CATALOG: Mapping[str, ExecutablePolicy] = {
    "7zip": ExecutablePolicy(
        "7zip", SEVEN_ZIP_EXECUTABLE_PATH, Path("D:\\"), _seven_zip_arguments,
        allowed_operation_types=frozenset({"read_open", "process"}), policy_class="archive",
        minimum_authority=AuthorityLevel.L1_READ_OPEN, capabilities=frozenset({"archive_read", "archive_create"}),
        authority_classifier=_seven_zip_authority, allow_cwd_descendants=True,
    ),
    "git": ExecutablePolicy(
        "git", GIT_EXECUTABLE_PATH, Path("D:\\"), _git_arguments,
        policy_class="git", minimum_authority=AuthorityLevel.L1_READ_OPEN,
        capabilities=frozenset({"read", "workspace_write", "network"}), authority_classifier=_git_authority,
        argument_transformer=_safe_git_arguments, allow_cwd_descendants=True,
    ),
    "python": ExecutablePolicy(
        "python", PYTHON_EXECUTABLE_PATH, Path("D:\\"), _nonempty_arguments,
        policy_class="build_or_script_runtime", minimum_authority=AuthorityLevel.L3_WORKSPACE_WRITE,
        capabilities=frozenset({"workspace_write", "network", "child_process"}), allow_cwd_descendants=True,
    ),
    "node": ExecutablePolicy(
        "node", NODE_EXECUTABLE_PATH, Path("D:\\"), _nonempty_arguments,
        policy_class="build_or_script_runtime", minimum_authority=AuthorityLevel.L3_WORKSPACE_WRITE,
        capabilities=frozenset({"workspace_write", "network", "child_process"}), allow_cwd_descendants=True,
    ),
    "everything": ExecutablePolicy(
        "everything", EVERYTHING_EXECUTABLE_PATH, Path("D:\\"), _everything_arguments,
        policy_class="readonly_cli", minimum_authority=AuthorityLevel.L1_READ_OPEN,
        capabilities=frozenset({"read", "search"}), allow_cwd_descendants=True,
    ),
}


def _required_authority(policy: ExecutablePolicy, operation_type: str) -> AuthorityLevel:
    if operation_type == "delete":
        raise AdmissionError("DELETE_HARD_DENY", "delete is hard denied")
    if operation_type == "system_admin":
        return AuthorityLevel.L5_SYSTEM_ADMIN
    if operation_type == "external_effect" or policy.network_policy != "none":
        return AuthorityLevel.L4_EXTERNAL_EFFECT
    if policy.write_scope != "none":
        return AuthorityLevel.L3_WORKSPACE_WRITE
    if operation_type == "query":
        return AuthorityLevel.L0_QUERY
    if operation_type == "read_open":
        return AuthorityLevel.L1_READ_OPEN
    if operation_type == "process":
        return AuthorityLevel.L2_CREATE_PROCESS
    raise AdmissionError("OPERATION_NOT_ALLOWED", "operation type is not allowed")


def _canonical_request(request: ProcessJobSpec | ProcessRequest) -> tuple[ProcessJobSpec, str | None]:
    if isinstance(request, ProcessJobSpec):
        return request, None
    return ProcessJobSpec(
        "process", request.executable_id, tuple(request.argv) if not isinstance(request.argv, str) else request.argv,
        Path(request.cwd), request.timeout_seconds, request.write_scope, request.network_policy,
    ), request.operation_type


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def approve_process_request(
    request: ProcessJobSpec | ProcessRequest, catalog: Mapping[str, ExecutablePolicy], config: RunnerConfig,
) -> ApprovedProcessSpec:
    """Resolve every executable property from Runner policy, never caller paths/hints."""
    canonical, legacy_operation_type = _canonical_request(request)
    if canonical.type != "process":
        raise AdmissionError("PROCESS_SPEC_INVALID", "job type must be process")
    if not isinstance(canonical.executable, str) or not canonical.executable:
        raise AdmissionError("EXECUTABLE_NOT_ALLOWED", "executable is not allowed")
    policy = catalog.get(canonical.executable)
    if policy is None:
        raise AdmissionError("EXECUTABLE_NOT_ALLOWED", "executable is not approved")
    if policy.executable_path is None or not policy.executable_path.is_file():
        raise AdmissionError("EXECUTABLE_UNAVAILABLE", "approved executable is unavailable")
    if isinstance(canonical.arguments, str) or not isinstance(canonical.arguments, (tuple, list)):
        raise AdmissionError("PROCESS_SPEC_INVALID", "argv must be a structured list")
    argv = tuple(canonical.arguments)
    if any(not isinstance(value, str) or "\x00" in value for value in argv):
        raise AdmissionError("PROCESS_SPEC_INVALID", "argv contains an invalid value")
    maximum_argument_length = policy.maximum_argument_string_length or config.maximum_argument_string_length
    if len(argv) > 128 or any(len(value) > maximum_argument_length for value in argv):
        raise AdmissionError("PROCESS_SPEC_INVALID", "argv exceeds configured limits")
    if not isinstance(canonical.timeout, int) or isinstance(canonical.timeout, bool):
        raise AdmissionError("PROCESS_SPEC_INVALID", "timeout is invalid")
    if not config.process_timeout_min_seconds <= canonical.timeout <= config.process_timeout_max_seconds:
        raise AdmissionError("PROCESS_TIMEOUT_NOT_ALLOWED", "timeout is outside Runner limits")
    requested_cwd = Path(canonical.cwd).resolve(strict=False)
    policy_cwd = policy.cwd.resolve(strict=False)
    if (policy.allow_cwd_descendants and not _within(requested_cwd, policy_cwd)) or (not policy.allow_cwd_descendants and requested_cwd != policy_cwd):
        raise AdmissionError("CWD_NOT_ALLOWED", "cwd is not approved")
    if not policy.argument_validator(argv):
        raise AdmissionError("ARGUMENTS_NOT_ALLOWED", "arguments are not approved")
    if legacy_operation_type is not None:
        allowed_operation_types = policy.allowed_operation_types or frozenset({policy.operation_type})
        if canonical.write_scope != policy.write_scope or canonical.network_policy != policy.network_policy or legacy_operation_type not in allowed_operation_types:
            raise AdmissionError("PROCESS_POLICY_MISMATCH", "process policy fields must match Runner policy")
        required = _required_authority(policy, legacy_operation_type)
    else:
        if canonical.write_scope not in {"none", "workspace"} or canonical.network_policy not in {"none", "external"}:
            raise AdmissionError("PROCESS_SPEC_INVALID", "scope or network policy is invalid")
        if canonical.write_scope == "workspace" and "workspace_write" not in policy.capabilities:
            raise AdmissionError("PROCESS_POLICY_MISMATCH", "workspace write is not supported by executable policy")
        if canonical.network_policy == "external" and "network" not in policy.capabilities:
            raise AdmissionError("PROCESS_POLICY_MISMATCH", "network access is not supported by executable policy")
        required = policy.authority_classifier(argv) if policy.authority_classifier is not None else policy.minimum_authority
        required = max(required, policy.minimum_authority)
        if canonical.write_scope == "workspace":
            required = max(required, AuthorityLevel.L3_WORKSPACE_WRITE)
        if canonical.network_policy == "external":
            required = max(required, AuthorityLevel.L4_EXTERNAL_EFFECT)
    if required == AuthorityLevel.L5_SYSTEM_ADMIN:
        raise AdmissionError("DENY", "system administration is denied")
    if required >= AuthorityLevel.L3_WORKSPACE_WRITE:
        raise AdmissionError("AUTHORIZATION_REQUIRED", "required authority is not enabled")
    approved_argv = policy.argument_transformer(argv) if policy.argument_transformer is not None else argv
    return ApprovedProcessSpec(
        policy.executable_id, policy.executable_path.resolve(strict=False), approved_argv,
        requested_cwd, canonical.timeout, canonical.write_scope,
        canonical.network_policy, required,
    )
