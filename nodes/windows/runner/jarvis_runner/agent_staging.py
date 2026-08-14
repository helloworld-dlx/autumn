"""Runner-owned workspace staging and CREATE/MODIFY-only publish primitive."""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import AGENT_STAGING_DIRECTORY_NAME, RunnerConfig
from .errors import RunnerError
from .security import _is_reparse_point, validate_controlled_write_path, validate_read_directory_path


@dataclass(frozen=True)
class StagingWorkspace:
    job_id: str
    real_workspace: Path
    base: Path
    work: Path


@dataclass(frozen=True)
class StagedChange:
    operation: str
    relative_path: Path


@dataclass(frozen=True)
class _Tree:
    files: dict[str, Path]
    directories: dict[str, Path]


class AgentStaging:
    """Internal primitive whose staging paths are always derived by Runner."""

    def __init__(self, config: RunnerConfig):
        self._config = config
        self._root = (config.runner_root.parent / AGENT_STAGING_DIRECTORY_NAME).absolute()
        validate_controlled_write_path(self._root, config)
        self._sessions: dict[str, StagingWorkspace] = {}

    def prepare(self, job_id: str, real_workspace: str | Path) -> StagingWorkspace:
        canonical_job_id = _canonical_job_id(job_id)
        if canonical_job_id in self._sessions:
            raise RunnerError("STAGING_ALREADY_EXISTS", "staging already exists for job")
        workspace = validate_read_directory_path(str(real_workspace), self._config)
        if _within(self._root, workspace) or _within(workspace, self._root):
            raise RunnerError("PATH_NOT_ALLOWED", "workspace overlaps Runner staging")
        _scan_tree(workspace)
        self._validate_runner_path(self._root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._validate_runner_path(self._root)

        job_root = self._root / canonical_job_id
        base = job_root / "base"
        work = job_root / "work"
        if job_root.exists() or _is_reparse_point(job_root):
            raise RunnerError("STAGING_ALREADY_EXISTS", "staging already exists for job")
        try:
            base.mkdir(parents=True)
            work.mkdir()
            _copy_tree(workspace, base)
            _copy_tree(base, work)
            session = StagingWorkspace(canonical_job_id, workspace, base, work)
            self._sessions[canonical_job_id] = session
            self._validate_session(session)
            return session
        except Exception:
            if job_root.exists() and not _is_reparse_point(job_root):
                shutil.rmtree(job_root)
            raise

    def build_change_set(self, job_id: str) -> tuple[StagedChange, ...]:
        session = self._session(job_id)
        base = _scan_tree(session.base)
        work = _scan_tree(session.work)
        changes: list[StagedChange] = []

        for key, relative in base.directories.items():
            work_relative = work.directories.get(key)
            if work_relative is None or work_relative != relative:
                changes.append(StagedChange("DELETE", relative))
        for key, relative in base.files.items():
            work_relative = work.files.get(key)
            if work_relative is None or work_relative != relative:
                changes.append(StagedChange("DELETE", relative))
            elif not _files_equal(session.base / relative, session.work / work_relative):
                changes.append(StagedChange("MODIFY", work_relative))
        for key, relative in work.files.items():
            if key not in base.files or base.files[key] != relative:
                changes.append(StagedChange("CREATE", relative))

        create_parents = {
            str(parent).casefold()
            for change in changes if change.operation == "CREATE"
            for parent in change.relative_path.parents if parent != Path(".")
        }
        unsupported_directories = [
            relative for key, relative in work.directories.items()
            if key not in base.directories and key not in create_parents
        ]
        if unsupported_directories:
            raise RunnerError("PUBLISH_DENIED", "standalone directory changes are not supported")
        return tuple(sorted(changes, key=lambda item: (str(item.relative_path).casefold(), item.operation)))

    def validate_publish(self, job_id: str) -> tuple[StagedChange, ...]:
        session = self._session(job_id)
        changes = self.build_change_set(job_id)
        if any(change.operation not in {"CREATE", "MODIFY"} for change in changes):
            raise RunnerError("PUBLISH_DENIED", "delete, rename, and move are not supported")

        workspace = validate_read_directory_path(str(session.real_workspace), self._config)
        if workspace != session.real_workspace:
            raise RunnerError("PUBLISH_DENIED", "real workspace identity changed")
        for change in changes:
            target = self._validate_target(session, change.relative_path)
            source = session.work / change.relative_path
            if change.operation == "CREATE":
                if target.exists() or _is_reparse_point(target):
                    raise RunnerError("PUBLISH_CONFLICT", "CREATE target now exists")
            else:
                base = session.base / change.relative_path
                if not _ordinary_file(target) or not _files_equal(base, target):
                    raise RunnerError("PUBLISH_CONFLICT", "MODIFY target changed after staging")
            if not _ordinary_file(source):
                raise RunnerError("PUBLISH_DENIED", "staged source is not an ordinary file")
        return changes

    def publish(self, job_id: str) -> tuple[StagedChange, ...]:
        session = self._session(job_id)
        changes = self.validate_publish(job_id)
        for change in changes:
            source = session.work / change.relative_path
            target = session.real_workspace / change.relative_path
            if change.operation == "CREATE":
                _create_parents(session.real_workspace, target.parent)
                with source.open("rb") as source_handle, target.open("xb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle)
                    target_handle.flush()
                    os.fsync(target_handle.fileno())
            else:
                temporary_name: str | None = None
                try:
                    with source.open("rb") as source_handle, tempfile.NamedTemporaryFile(
                        mode="wb", dir=target.parent, prefix=".jarvis-publish-", delete=False
                    ) as target_handle:
                        temporary_name = target_handle.name
                        shutil.copyfileobj(source_handle, target_handle)
                        target_handle.flush()
                        os.fsync(target_handle.fileno())
                    os.replace(temporary_name, target)
                    temporary_name = None
                finally:
                    if temporary_name is not None:
                        Path(temporary_name).unlink(missing_ok=True)
        return changes

    def cleanup(self, job_id: str) -> None:
        session = self._session(job_id)
        self._validate_session(session)
        _scan_tree(session.base)
        _scan_tree(session.work)
        shutil.rmtree(session.base.parent)
        del self._sessions[session.job_id]

    def _session(self, job_id: str) -> StagingWorkspace:
        canonical_job_id = _canonical_job_id(job_id)
        session = self._sessions.get(canonical_job_id)
        if session is None:
            raise RunnerError("STAGING_NOT_FOUND", "Runner-owned staging was not found")
        self._validate_session(session)
        return session

    def _validate_session(self, session: StagingWorkspace) -> None:
        expected = self._root / session.job_id
        if session.base != expected / "base" or session.work != expected / "work":
            raise RunnerError("STAGING_NOT_OWNED", "staging path is not Runner-owned")
        for path in (self._root, expected, session.base, session.work):
            self._validate_runner_path(path)
        if not session.base.is_dir() or not session.work.is_dir():
            raise RunnerError("STAGING_NOT_FOUND", "Runner-owned staging was not found")

    def _validate_runner_path(self, path: Path) -> None:
        candidate = validate_controlled_write_path(path, self._config)
        current = self._config.workspace_root.absolute()
        try:
            relative = candidate.absolute().relative_to(current)
        except ValueError as error:
            raise RunnerError("STAGING_NOT_OWNED", "staging path is not Runner-owned") from error
        if _is_reparse_point(current):
            raise RunnerError("PATH_NOT_ALLOWED", "Runner staging crosses a reparse point")
        for part in relative.parts:
            current = current / part
            if _is_reparse_point(current):
                raise RunnerError("PATH_NOT_ALLOWED", "Runner staging crosses a reparse point")

    def _validate_target(self, session: StagingWorkspace, relative: Path) -> Path:
        if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} or ":" in part for part in relative.parts):
            raise RunnerError("PUBLISH_DENIED", "publish target is invalid")
        target = session.real_workspace.joinpath(*relative.parts)
        try:
            target.resolve(strict=False).relative_to(session.real_workspace.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise RunnerError("PUBLISH_DENIED", "publish target escaped real workspace") from error
        current = session.real_workspace
        for part in relative.parts:
            current = current / part
            if _is_reparse_point(current):
                raise RunnerError("PUBLISH_DENIED", "publish target crosses a reparse point")
            if current != target and current.exists() and not current.is_dir():
                raise RunnerError("PUBLISH_CONFLICT", "publish parent is not a directory")
        return target


def _canonical_job_id(job_id: object) -> str:
    if not isinstance(job_id, str):
        raise RunnerError("JOB_ID_INVALID", "job_id is invalid")
    try:
        parsed = uuid.UUID(job_id)
    except (ValueError, AttributeError) as error:
        raise RunnerError("JOB_ID_INVALID", "job_id is invalid") from error
    if str(parsed) != job_id:
        raise RunnerError("JOB_ID_INVALID", "job_id is invalid")
    return job_id


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.absolute().relative_to(root.absolute())
    except ValueError:
        return False
    return True


def _key(relative: Path) -> str:
    return str(relative).casefold()


def _scan_tree(root: Path) -> _Tree:
    if _is_reparse_point(root) or not root.is_dir():
        raise RunnerError("PATH_NOT_ALLOWED", "tree root is not an ordinary directory")
    files: dict[str, Path] = {}
    directories: dict[str, Path] = {}
    pending = [root]
    try:
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    relative = path.relative_to(root)
                    if any(":" in part for part in relative.parts) or _is_reparse_point(path):
                        raise RunnerError("PATH_NOT_ALLOWED", "tree contains an unsafe path")
                    mode = entry.stat(follow_symlinks=False).st_mode
                    key = _key(relative)
                    if stat.S_ISDIR(mode):
                        directories[key] = relative
                        pending.append(path)
                    elif stat.S_ISREG(mode):
                        files[key] = relative
                    else:
                        raise RunnerError("PATH_NOT_ALLOWED", "tree contains a non-ordinary entry")
    except RunnerError:
        raise
    except OSError as error:
        raise RunnerError("PATH_NOT_ALLOWED", "tree could not be safely inspected") from error
    return _Tree(files, directories)


def _copy_tree(source: Path, destination: Path) -> None:
    tree = _scan_tree(source)
    for relative in sorted(tree.directories.values(), key=lambda item: len(item.parts)):
        (destination / relative).mkdir()
    for relative in sorted(tree.files.values(), key=lambda item: str(item).casefold()):
        source_file = source / relative
        if not _ordinary_file(source_file):
            raise RunnerError("PATH_NOT_ALLOWED", "source changed during staging")
        try:
            with source_file.open("rb") as source_handle, (destination / relative).open("xb") as destination_handle:
                shutil.copyfileobj(source_handle, destination_handle)
        except OSError as error:
            raise RunnerError("PATH_NOT_ALLOWED", "source changed during staging") from error
    _scan_tree(destination)


def _ordinary_file(path: Path) -> bool:
    if _is_reparse_point(path):
        return False
    try:
        return stat.S_ISREG(path.stat(follow_symlinks=False).st_mode)
    except OSError:
        return False


def _files_equal(left: Path, right: Path) -> bool:
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_handle, right.open("rb") as right_handle:
            while True:
                left_chunk = left_handle.read(1024 * 1024)
                right_chunk = right_handle.read(1024 * 1024)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError as error:
        raise RunnerError("PUBLISH_DENIED", "file content could not be compared") from error


def _create_parents(workspace: Path, parent: Path) -> None:
    relative = parent.relative_to(workspace)
    current = workspace
    for part in relative.parts:
        current = current / part
        if current.exists():
            if _is_reparse_point(current) or not current.is_dir():
                raise RunnerError("PUBLISH_CONFLICT", "publish parent is unsafe")
        else:
            current.mkdir()
