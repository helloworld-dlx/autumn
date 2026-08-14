import json
import tempfile
import unittest
from pathlib import Path

from jarvis_runner.config import RunnerConfig
from jarvis_runner.errors import RunnerError
from jarvis_runner.worker_control import WorkerControlState


class WorkerControlStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r"D:\JarvisWorkspace\JarvisRunner\work")
        self.root = Path(self.temp.name)
        self.config = RunnerConfig(
            workspace_root=self.root.parent, runner_root=self.root,
            audit_log=self.root / "logs" / "audit.jsonl",
            job_state_path=self.root / "state" / "jobs.json",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_default_pause_persistence_reload_and_resume(self):
        control = WorkerControlState(self.config)
        self.assertFalse(control.workers_paused)

        control.pause()
        control.pause()
        self.assertTrue(control.workers_paused)
        self.assertEqual(
            json.loads((self.root / "state" / "workers.json").read_text(encoding="utf-8")),
            {"workers_paused": True},
        )
        self.assertTrue(WorkerControlState(self.config).workers_paused)

        control.resume()
        control.resume()
        self.assertFalse(WorkerControlState(self.config).workers_paused)

    def test_malformed_state_fails_safe_until_explicit_resume(self):
        state_path = self.root / "state" / "workers.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text('{"workers_paused":"false"}', encoding="utf-8")

        control = WorkerControlState(self.config)
        self.assertTrue(control.workers_paused)
        with self.assertRaises(RunnerError) as caught:
            with control.admit_submission():
                pass
        self.assertEqual(caught.exception.code, "WORKERS_PAUSED")

        control.resume()
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), {"workers_paused": False})


if __name__ == "__main__":
    unittest.main()
