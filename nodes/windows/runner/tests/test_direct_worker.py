import tempfile
import time
import unittest
import zipfile
import sys
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.authority import AdmissionError, AuthorityLevel, ExecutablePolicy, PRODUCTION_EXECUTABLE_CATALOG, SEVEN_ZIP_EXECUTABLE_PATH
from jarvis_runner.config import RunnerConfig
from jarvis_runner.direct_worker import DIRECT_WORKER_OPERATIONS, DirectWorkerService, required_authority_for_operation
from jarvis_runner.errors import RunnerError
from jarvis_runner.models import ProcessJobSpec


class DirectWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r"D:\JarvisWorkspace\JarvisRunner\work")
        self.root = Path(self.temp.name)
        runner_root = self.root / "JarvisRunner"
        config = RunnerConfig(workspace_root=self.root, runner_root=runner_root, audit_log=runner_root / "logs" / "audit.jsonl", job_state_path=runner_root / "state" / "jobs.json")
        self.worker = DirectWorkerService(config)

    def tearDown(self):
        self.temp.cleanup()

    def _terminal(self, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            record = self.worker.store.get(job_id)
            if record and record.result is not None:
                return record
            time.sleep(0.05)
        self.fail("Direct Worker job did not finish")

    def test_catalog_contract_and_authority_are_fixed(self):
        self.assertEqual(set(PRODUCTION_EXECUTABLE_CATALOG), {"7zip", "git", "python", "node", "everything"})
        self.assertEqual(DIRECT_WORKER_OPERATIONS, {"archive.list", "archive.create"})
        self.assertNotIn("archive.extract", DIRECT_WORKER_OPERATIONS)
        self.assertEqual(PRODUCTION_EXECUTABLE_CATALOG["7zip"].executable_path, SEVEN_ZIP_EXECUTABLE_PATH)
        self.assertEqual(required_authority_for_operation("archive.list"), AuthorityLevel.L1_READ_OPEN)
        self.assertEqual(required_authority_for_operation("archive.create"), AuthorityLevel.L2_CREATE_PROCESS)
        self.assertFalse(hasattr(self.worker, "execute"))
        with self.assertRaisesRegex(RunnerError, "requires exactly"):
            self.worker.submit_direct_job("archive.list", {"archive_path": r"D:\x.zip", "argv": ["x"]})
        with self.assertRaisesRegex(RunnerError, "requires source_paths"):
            self.worker.submit_direct_job("archive.create", {"source_paths": [], "output_archive": r"D:\x.zip", "requested_authority": "L0"})

    def test_create_new_zip_then_list_smoke_and_bounded_result(self):
        source = self.root / "source"; source.mkdir()
        (source / "probe.txt").write_text("direct worker smoke", encoding="utf-8")
        archive = self.root / "probe.zip"
        created = self._terminal(self.worker.submit_direct_job("archive.create", {"source_paths": [str(source)], "output_archive": str(archive)}).job_id)
        self.assertEqual(created.status, "succeeded")
        self.assertTrue(archive.is_file())
        listed = self._terminal(self.worker.submit_direct_job("archive.list", {"archive_path": str(archive)}).job_id)
        self.assertEqual(listed.status, "succeeded")
        self.assertIn("probe.txt", listed.result.stdout)
        self.assertLessEqual(len(listed.result.stdout.encode("utf-8")), 8192)
        with self.assertRaisesRegex(RunnerError, "already exists"):
            self.worker.submit_direct_job("archive.create", {"source_paths": [str(source)], "output_archive": str(archive)})

    def test_non_d_paths_ads_and_reparse_are_rejected(self):
        archive = self.root / "input.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr("one.txt", "one")
        for value in (r"C:\input.zip", r"\\server\share\input.zip", str(archive) + ":hidden"):
            with self.subTest(value=value):
                with self.assertRaises(RunnerError):
                    self.worker.submit_direct_job("archive.list", {"archive_path": value})
        plain_file = self.root / "plain.txt"; plain_file.write_text("not an archive", encoding="utf-8")
        with self.assertRaisesRegex(RunnerError, "only .zip"):
            self.worker.submit_direct_job("archive.list", {"archive_path": str(plain_file)})
        with patch("jarvis_runner.direct_worker._is_reparse_point", side_effect=lambda path: path == self.root):
            with self.assertRaises(RunnerError):
                self.worker.submit_direct_job("archive.create", {"source_paths": [str(archive)], "output_archive": str(self.root / "new.zip")})

    def test_new_executable_profile_uses_same_worker_job_and_supervisor(self):
        helper = Path(__file__).parent / "helpers" / "worker_probe.py"
        empty_worker = DirectWorkerService(self.worker.config, catalog={})
        unavailable_spec = ProcessJobSpec("process", "probe", ("success",), helper.parent, 5, "none", "none")
        with self.assertRaises(AdmissionError) as caught:
            empty_worker.submit_process_job(unavailable_spec)
        self.assertEqual(caught.exception.code, "EXECUTABLE_NOT_ALLOWED")
        self.assertEqual(empty_worker.store.list_records(), ())
        policy = ExecutablePolicy(
            "probe", Path(sys.executable), helper.parent,
            lambda argv: argv == ("-I", "-B", str(helper), "success"),
            test_only=True, policy_class="generic_process", minimum_authority=AuthorityLevel.L2_CREATE_PROCESS,
        )
        worker = DirectWorkerService(self.worker.config, catalog={"probe": policy})
        spec = ProcessJobSpec("process", "probe", ("-I", "-B", str(helper), "success"), helper.parent, 5, "none", "none")
        terminal = self._terminal_for(worker, worker.submit_process_job(spec).job_id)
        self.assertEqual((terminal.job_type, terminal.backend, terminal.status), ("process", "probe", "succeeded"))

    def _terminal_for(self, worker, job_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            record = worker.store.get(job_id)
            if record and record.result is not None:
                return record
            time.sleep(0.05)
        self.fail("generic process job did not finish")
