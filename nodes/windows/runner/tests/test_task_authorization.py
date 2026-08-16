import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis_runner.authority import AuthorityLevel
from jarvis_runner.config import RunnerConfig
from jarvis_runner.errors import RunnerError
from jarvis_runner.task_authorization import (
    AGENT_L3_PUBLISH_EFFECTS, AUTHORIZATION_TTL, TaskAuthorizationStore,
)


class _Clock:
    def __init__(self):
        self.now = datetime(2026, 8, 11, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


class TaskAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        runner_root = root / "JarvisWorkspace" / "JarvisRunner"
        self.config = RunnerConfig(
            workspace_root=runner_root.parent, runner_root=runner_root,
            audit_log=runner_root / "logs" / "audit.jsonl",
            job_state_path=runner_root / "state" / "jobs.json", read_root=root,
        )
        self.clock = _Clock()
        self.store = TaskAuthorizationStore(self.config, clock=self.clock)

    def tearDown(self):
        self.temp.cleanup()

    def _create(self):
        return self.store.create_request(
            subject="autumn:user", adapter="codex", real_workspace=self.workspace,
            task_summary="  update   the\nreadme  ", network_policy="none",
        )

    def test_request_binds_exact_workspace_adapter_task_and_effects(self):
        request = self._create()
        uuid.UUID(request.authorization_request_id)
        self.assertEqual(request.subject, "autumn:user")
        self.assertEqual(request.adapter, "codex")
        self.assertEqual(request.real_workspace, self.workspace.resolve())
        self.assertEqual(request.task_summary, "update the readme")
        self.assertEqual(request.allowed_publish_effects, AGENT_L3_PUBLISH_EFFECTS)
        self.assertEqual(request.network_policy, "none")
        self.assertEqual(request.authority_level, AuthorityLevel.L3_WORKSPACE_WRITE)
        self.assertEqual(request.expires_at - request.created_at, AUTHORIZATION_TTL)

    def test_approval_preserves_frozen_request_and_happens_once(self):
        request = self._create()
        approved = self.store.approve(request.authorization_request_id, subject=request.subject)
        frozen = ("subject", "adapter", "real_workspace", "task_summary", "allowed_publish_effects", "network_policy", "authority_level")
        self.assertEqual(tuple(getattr(approved, field) for field in frozen), tuple(getattr(request, field) for field in frozen))
        self.assertEqual(approved.status, "approved")
        with self.assertRaises(RunnerError) as caught:
            self.store.approve(request.authorization_request_id, subject=request.subject)
        self.assertEqual(caught.exception.code, "AUTHORIZATION_ALREADY_APPROVED")

    def test_consumption_is_single_use_and_cannot_replay(self):
        request = self._create()
        with self.assertRaises(RunnerError) as caught:
            self.store.consume(request.authorization_request_id, subject=request.subject)
        self.assertEqual(caught.exception.code, "AUTHORIZATION_NOT_APPROVED")
        self.store.approve(request.authorization_request_id, subject=request.subject)
        consumed = self.store.consume(request.authorization_request_id, subject=request.subject)
        self.assertEqual(consumed.status, "consumed")
        with self.assertRaises(RunnerError) as caught:
            self.store.consume(request.authorization_request_id, subject=request.subject)
        self.assertEqual(caught.exception.code, "AUTHORIZATION_CONSUMED")

    def test_expired_request_is_rejected(self):
        request = self._create()
        self.clock.now += timedelta(minutes=10)
        with self.assertRaises(RunnerError) as caught:
            self.store.approve(request.authorization_request_id, subject=request.subject)
        self.assertEqual(caught.exception.code, "AUTHORIZATION_EXPIRED")

    def test_wrong_subject_and_unknown_request_are_rejected(self):
        request = self._create()
        with self.assertRaises(RunnerError) as caught:
            self.store.approve(request.authorization_request_id, subject="autumn:other")
        self.assertEqual(caught.exception.code, "AUTHORIZATION_SUBJECT_MISMATCH")
        with self.assertRaises(RunnerError) as caught:
            self.store.approve(str(uuid.uuid4()), subject=request.subject)
        self.assertEqual(caught.exception.code, "AUTHORIZATION_NOT_FOUND")

    def test_l3_core_cannot_grant_delete_l4_or_l5(self):
        with self.assertRaises(RunnerError) as caught:
            self.store.create_request(
                subject="autumn:user", adapter="codex", real_workspace=self.workspace,
                task_summary="network task", network_policy="external",
            )
        self.assertEqual(caught.exception.code, "L4_NOT_AUTHORIZED")
        request = self._create()
        self.assertNotIn("DELETE", request.allowed_publish_effects)
        with self.assertRaises(TypeError):
            self.store.create_request(
                subject="autumn:user", adapter="codex", real_workspace=self.workspace,
                task_summary="delete task", allowed_publish_effects=("DELETE",),
            )
        with self.assertRaises(TypeError):
            self.store.create_request(
                subject="autumn:user", adapter="codex", real_workspace=self.workspace,
                task_summary="admin task", authority_level=AuthorityLevel.L5_SYSTEM_ADMIN,
            )

    def test_list_pending_returns_only_live_pending_requests(self):
        first = self._create()
        second = self.store.create_request(
            subject="autumn:user", adapter="codex", real_workspace=self.workspace,
            task_summary="second task", network_policy="none",
        )
        self.store.approve(second.authorization_request_id, subject=second.subject)
        pending = self.store.list_pending()
        self.assertEqual([item.authorization_request_id for item in pending], [first.authorization_request_id])
        self.clock.now += timedelta(minutes=10)
        self.assertEqual(self.store.list_pending(), ())

    def test_new_store_cannot_see_pre_restart_requests(self):
        request = self._create()
        restarted = TaskAuthorizationStore(self.config, clock=self.clock)
        with self.assertRaises(RunnerError) as caught:
            restarted.approve(request.authorization_request_id, subject=request.subject)
        self.assertEqual(caught.exception.code, "AUTHORIZATION_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
