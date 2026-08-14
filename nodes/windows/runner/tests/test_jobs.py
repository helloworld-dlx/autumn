import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jarvis_runner.audit import append_job_audit_event
from jarvis_runner.config import RunnerConfig
from jarvis_runner.jobs import JobStateError, JobStore
from jarvis_runner.models import JobResult


class JobStoreTests(unittest.TestCase):
    def _config(self, root: Path, *, max_records: int = 4, ttl_seconds: int = 86400) -> RunnerConfig:
        runner_root = root / "JarvisRunner"
        return RunnerConfig(
            workspace_root=root, runner_root=runner_root, audit_log=runner_root / "logs" / "audit.jsonl",
            job_state_path=runner_root / "state" / "jobs.json", job_max_records=max_records,
            job_terminal_ttl_seconds=ttl_seconds,
        )

    def test_generated_ids_are_unique(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(self._config(Path(temp), max_records=100))
            records = [store.create("direct", "placeholder") for _ in range(50)]
            self.assertEqual(len({record.job_id for record in records}), 50)

    def test_valid_transitions_and_terminal_immutability(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(self._config(Path(temp)))
            job = store.create("direct", "placeholder")
            running = store.transition(job.job_id, "running")
            done = store.transition(job.job_id, "succeeded")
            self.assertIsNotNone(running.started_at)
            self.assertIsNotNone(done.finished_at)
            with self.assertRaises(JobStateError):
                store.transition(job.job_id, "failed")

    def test_all_canonical_terminal_transitions_are_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(self._config(Path(temp), max_records=10))
            queued = store.create("direct", "placeholder")
            self.assertEqual(store.transition(queued.job_id, "cancelled").status, "cancelled")
            for target in ("succeeded", "failed", "cancelled", "timed_out", "interrupted_by_restart"):
                job = store.create("direct", "placeholder")
                store.transition(job.job_id, "running")
                self.assertEqual(store.transition(job.job_id, target).status, target)

    def test_invalid_transitions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(self._config(Path(temp)))
            job = store.create("direct", "placeholder")
            with self.assertRaises(JobStateError): store.transition(job.job_id, "succeeded")
            with self.assertRaises(JobStateError): store.transition(job.job_id, "queued")

    def test_bounded_store_prunes_terminal_before_rejecting_new_record(self):
        with tempfile.TemporaryDirectory() as temp:
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            store = JobStore(self._config(Path(temp), max_records=2, ttl_seconds=1))
            old = store.create("direct", "placeholder", now=start)
            store.transition(old.job_id, "cancelled", now=start)
            active = store.create("direct", "placeholder", now=start)
            fresh = store.create("direct", "placeholder", now=start + timedelta(seconds=2))
            self.assertIsNone(store.get(old.job_id))
            self.assertIsNotNone(store.get(active.job_id)); self.assertIsNotNone(store.get(fresh.job_id))
            with self.assertRaises(JobStateError): store.create("direct", "placeholder")

    def test_result_is_bounded_and_uses_terminal_status(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(self._config(Path(temp)))
            job = store.create("direct", "placeholder")
            store.transition(job.job_id, "running"); store.transition(job.job_id, "succeeded")
            result = JobResult("succeeded", "done", "ok", "", 0, None, {"source": "test"})
            saved = store.set_result(job.job_id, result)
            self.assertEqual(saved.result, result)
            with self.assertRaises(JobStateError):
                store.set_result(job.job_id, JobResult("succeeded", stdout="x" * 8193))

    def test_persistence_preserves_terminal_and_recovers_active_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp), max_records=10)
            store = JobStore(config)
            terminal = store.create("direct", "placeholder")
            store.transition(terminal.job_id, "cancelled")
            queued = store.create("direct", "placeholder")
            running = store.create("direct", "placeholder")
            store.transition(running.job_id, "running")
            recovered = JobStore(config)
            recovery_time = datetime(2026, 2, 3, tzinfo=timezone.utc)
            recovered.load(recovery_time=recovery_time)
            self.assertEqual(recovered.get(terminal.job_id).status, "cancelled")
            for job_id in (queued.job_id, running.job_id):
                record = recovered.get(job_id)
                self.assertEqual(record.status, "interrupted_by_restart")
                self.assertEqual(record.finished_at, recovery_time.isoformat())
                self.assertEqual(record.error_code, "INTERRUPTED_BY_RESTART")

    def test_job_audit_event_excludes_result_streams(self):
        with tempfile.TemporaryDirectory() as temp:
            config = self._config(Path(temp))
            append_job_audit_event("job-1", "job_submitted", "queued", None, config)
            row = json.loads(config.audit_log.read_text(encoding="utf-8"))
            self.assertEqual(row["action"], "job_submitted")
            self.assertNotIn("stdout", row); self.assertNotIn("stderr", row)
