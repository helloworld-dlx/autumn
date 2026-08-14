import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from jarvis_runner.authority import ExecutablePolicy, ProcessRequest
from jarvis_runner.config import RunnerConfig
from jarvis_runner.jobs import JobStore
from jarvis_runner.models import JobResult
from jarvis_runner.process_supervisor import ProcessSupervisor
from jarvis_runner.programs import PROGRAM_STDERR_MAX_BYTES, PROGRAM_STDOUT_MAX_BYTES


class ProcessSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = RunnerConfig(
            workspace_root=root, runner_root=root / "JarvisRunner", audit_log=root / "JarvisRunner" / "logs" / "audit.jsonl",
            job_state_path=root / "JarvisRunner" / "state" / "jobs.json", process_timeout_min_seconds=1, process_timeout_max_seconds=3,
        )
        self.store = JobStore(self.config)
        self.helper = Path(__file__).parent / "helpers" / "worker_probe.py"
        self.cwd = self.helper.parent
        self.policy = ExecutablePolicy(
            "worker_probe", Path(sys.executable), self.cwd,
            lambda argv: len(argv) in (1, 2) and argv[0] in {"success", "fail", "sleep", "output", "spawn-child"}, test_only=True,
        )
        self.supervisor = ProcessSupervisor(self.store, self.config, catalog={"worker_probe": self.policy})

    def tearDown(self):
        self.temp.cleanup()

    def _start(self, *argv, timeout=1, completion_hook=None):
        job = self.store.create("direct", "test-only")
        request = ProcessRequest("worker_probe", ("-I", "-B", str(self.helper), *argv), self.cwd, timeout)
        # The test-only policy permits only the fixed interpreter preamble plus probe arguments.
        self.policy = ExecutablePolicy("worker_probe", Path(sys.executable), self.cwd, self._allowed_probe_argv, test_only=True)
        self.supervisor._catalog = {"worker_probe": self.policy}
        self.supervisor.start(job.job_id, request, completion_hook=completion_hook)
        return job.job_id

    def _allowed_probe_argv(self, argv):
        return len(argv) in (4, 5) and argv[:3] == ("-I", "-B", str(self.helper)) and argv[3] in {"success", "fail", "sleep", "output", "spawn-child"}

    def _terminal(self, job_id, seconds=8):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            record = self.store.get(job_id)
            if record is not None and record.status in {"succeeded", "failed", "cancelled", "timed_out"} and record.result is not None:
                return record
            time.sleep(0.05)
        self.fail("job did not reach terminal state")

    def test_success_nonzero_and_bounded_output(self):
        succeeded = self._terminal(self._start("success"))
        failed = self._terminal(self._start("fail"))
        output = self._terminal(self._start("output", "9000"))
        self.assertEqual(succeeded.status, "succeeded")
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.result.exit_code, 7)
        self.assertLessEqual(len(output.result.stdout.encode("utf-8")), PROGRAM_STDOUT_MAX_BYTES)
        self.assertLessEqual(len(output.result.stderr.encode("utf-8")), PROGRAM_STDERR_MAX_BYTES)
        self.assertTrue(output.result.metadata["stdout_truncated"])
        self.assertTrue(output.result.metadata["stderr_truncated"])

    def test_timeout_and_cancel_terminate_process_trees(self):
        timed_out = self._terminal(self._start("sleep", "5", timeout=1))
        self.assertEqual(timed_out.status, "timed_out")
        child_job = self._start("spawn-child", timeout=3)
        child_pid = self._child_pid(child_job)
        self.supervisor.cancel(child_job)
        cancelled = self._terminal(child_job)
        self.assertEqual(cancelled.status, "cancelled")
        self._assert_process_gone(child_pid)

    def test_completion_hook_can_gate_process_success(self):
        def deny_publish(job_id, result):
            del job_id, result
            return JobResult("failed", "publish denied", error_code="PUBLISH_DENIED")

        record = self._terminal(self._start("success", completion_hook=deny_publish))
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.result.error_code, "PUBLISH_DENIED")

    def _child_pid(self, job_id):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            record = self.store.get(job_id)
            active = self.supervisor._active.get(job_id)
            if active and active.stdout.data:
                return int(bytes(active.stdout.data).decode("utf-8").strip())
            time.sleep(0.05)
        self.fail("child pid was not observed")

    def _assert_process_gone(self, pid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            listing = subprocess.run(
                [r"C:\Windows\System32\tasklist.exe", "/FI", f"PID eq {pid}", "/NH"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False, check=False, timeout=5,
            ).stdout.decode("utf-8", errors="replace")
            if str(pid) not in listing:
                return
            time.sleep(0.05)
        self.fail("child process remained after tree termination")
