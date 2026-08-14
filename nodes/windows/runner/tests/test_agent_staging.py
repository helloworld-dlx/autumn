import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.agent_staging import AgentStaging
from jarvis_runner.config import RunnerConfig
from jarvis_runner.errors import RunnerError


class AgentStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        runner_root = root / "JarvisWorkspace" / "JarvisRunner"
        self.workspace = root / "real-workspace"
        self.workspace.mkdir()
        self.config = RunnerConfig(
            workspace_root=runner_root.parent,
            runner_root=runner_root,
            audit_log=runner_root / "logs" / "audit.jsonl",
            job_state_path=runner_root / "state" / "jobs.json",
            read_root=root,
        )
        self.staging = AgentStaging(self.config)

    def tearDown(self):
        self.temp.cleanup()

    def _prepare(self):
        return self.staging.prepare(str(uuid.uuid4()), self.workspace)

    def test_prepare_creates_independent_base_and_work(self):
        (self.workspace / "a.txt").write_text("original", encoding="utf-8")
        session = self._prepare()
        (session.work / "a.txt").write_text("agent", encoding="utf-8")
        self.assertEqual((session.base / "a.txt").read_text(encoding="utf-8"), "original")
        self.assertEqual((self.workspace / "a.txt").read_text(encoding="utf-8"), "original")

    def test_create_change_publishes_new_file_and_parent(self):
        session = self._prepare()
        (session.work / "new").mkdir()
        (session.work / "new" / "created.txt").write_text("created", encoding="utf-8")
        changes = self.staging.publish(session.job_id)
        self.assertEqual([(change.operation, str(change.relative_path)) for change in changes], [("CREATE", str(Path("new") / "created.txt"))])
        self.assertEqual((self.workspace / "new" / "created.txt").read_text(encoding="utf-8"), "created")

    def test_modify_change_publishes_changed_content(self):
        (self.workspace / "a.txt").write_text("base", encoding="utf-8")
        session = self._prepare()
        (session.work / "a.txt").write_text("modified", encoding="utf-8")
        changes = self.staging.publish(session.job_id)
        self.assertEqual(changes[0].operation, "MODIFY")
        self.assertEqual((self.workspace / "a.txt").read_text(encoding="utf-8"), "modified")

    def test_delete_is_denied_and_real_file_remains(self):
        (self.workspace / "keep.txt").write_text("keep", encoding="utf-8")
        session = self._prepare()
        (session.work / "keep.txt").unlink()
        with self.assertRaisesRegex(RunnerError, "delete, rename, and move") as caught:
            self.staging.publish(session.job_id)
        self.assertEqual(caught.exception.code, "PUBLISH_DENIED")
        self.assertEqual((self.workspace / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_external_conflict_denies_all_changes_before_writing(self):
        (self.workspace / "existing.txt").write_text("base", encoding="utf-8")
        session = self._prepare()
        (session.work / "existing.txt").write_text("agent", encoding="utf-8")
        (session.work / "new.txt").write_text("new", encoding="utf-8")
        (self.workspace / "existing.txt").write_text("user", encoding="utf-8")
        with self.assertRaises(RunnerError) as caught:
            self.staging.publish(session.job_id)
        self.assertEqual(caught.exception.code, "PUBLISH_CONFLICT")
        self.assertEqual((self.workspace / "existing.txt").read_text(encoding="utf-8"), "user")
        self.assertFalse((self.workspace / "new.txt").exists())

    def test_scope_escape_and_reparse_tree_are_denied(self):
        outside = self.workspace.parent / "outside"
        outside.mkdir()
        with self.assertRaises(RunnerError) as caught:
            self.staging.prepare(str(uuid.uuid4()), str(self.workspace / ".." / "outside"))
        self.assertEqual(caught.exception.code, "PATH_NOT_ALLOWED")

        blocked = self.workspace / "blocked"
        blocked.write_text("x", encoding="utf-8")
        real_is_reparse = __import__("jarvis_runner.agent_staging", fromlist=["_is_reparse_point"])._is_reparse_point
        with patch("jarvis_runner.agent_staging._is_reparse_point", side_effect=lambda path: Path(path) == blocked or real_is_reparse(path)):
            with self.assertRaises(RunnerError) as caught:
                self._prepare()
        self.assertEqual(caught.exception.code, "PATH_NOT_ALLOWED")


if __name__ == "__main__":
    unittest.main()
