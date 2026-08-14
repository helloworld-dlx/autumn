import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.cli import execute_request
from jarvis_runner.config import RunnerConfig
from jarvis_runner.errors import RunnerError
from jarvis_runner.models import ActionRequest
from jarvis_runner.programs import ProgramSpec, program_list, program_run
import jarvis_runner.programs as programs


class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = RunnerConfig(workspace_root=root, runner_root=root / "JarvisRunner", audit_log=root / "JarvisRunner" / "logs" / "audit.jsonl")

    def tearDown(self):
        self.temp.cleanup()

    def _temporary_program(self, source: str, *, expected_sha256: str | None = None, timeout_seconds: int = 5, stdout_max_bytes: int = 8192, stderr_max_bytes: int = 8192):
        root = Path(self.temp.name) / "JarvisScripts"
        root.mkdir(exist_ok=True)
        path = root / "hello_jarvis.py"
        path.write_text(source, encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        spec = ProgramSpec(
            program_id="hello_jarvis",
            path=path,
            description="test program",
            expected_sha256=expected_sha256 or digest,
            timeout_seconds=timeout_seconds,
            stdout_max_bytes=stdout_max_bytes,
            stderr_max_bytes=stderr_max_bytes,
        )
        return root, spec

    def _run_temporary_program(self, source: str, **kwargs):
        root, spec = self._temporary_program(source, **kwargs)
        with patch.object(programs, "PROGRAM_ROOT", root), patch.object(programs, "PROGRAM_REGISTRY", {"hello_jarvis": spec}):
            return program_run({"program_id": "hello_jarvis"}, self.config)

    def test_program_list_returns_only_limited_hello_metadata(self):
        result = program_list({}, self.config)
        self.assertEqual([item["program_id"] for item in result["programs"]], ["hello_jarvis"])
        self.assertNotIn("expected_sha256", result["programs"][0])
        self.assertNotIn("path", result["programs"][0])
        self.assertFalse(result["programs"][0]["accepts_arguments"])
        self.assertTrue(result["programs"][0]["read_only"])

    def test_program_list_rejects_nonempty_arguments(self):
        with self.assertRaises(ValueError):
            program_list({"program_id": "hello_jarvis"}, self.config)

    def test_hello_program_runs_and_returns_json(self):
        request = ActionRequest("program-normal", "program.run", {"program_id": "hello_jarvis"}, "test")
        result = execute_request(request, self.config)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.output["execution_status"], "succeeded")
        self.assertEqual(result.output["exit_code"], 0)
        self.assertFalse(result.output["timed_out"])
        self.assertFalse(result.output["stdout_truncated"])
        payload = json.loads(result.output["stdout"])
        self.assertEqual(set(payload), {"message", "timestamp", "computer_name", "python_version"})

    def test_program_run_uses_fixed_interpreter_arguments_and_no_shell(self):
        with patch.object(programs.subprocess, "Popen", wraps=programs.subprocess.Popen) as popen:
            result = execute_request(ActionRequest("program-argv", "program.run", {"program_id": "hello_jarvis"}, "test"), self.config)
        self.assertEqual(result.status, "success")
        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(command[:3], [sys.executable, "-I", "-B"])
        self.assertEqual(len(command), 4)
        self.assertFalse(options["shell"])
        self.assertEqual(options["cwd"], r"D:\JarvisScripts")
        self.assertIs(options["stdin"], programs.subprocess.DEVNULL)
        self.assertIs(options["stdout"], programs.subprocess.PIPE)
        self.assertIs(options["stderr"], programs.subprocess.PIPE)

    def test_program_run_rejects_unknown_and_malformed_arguments(self):
        with self.assertRaises(RunnerError) as unknown:
            program_run({"program_id": "other_program"}, self.config)
        self.assertEqual(unknown.exception.code, "PROGRAM_NOT_ALLOWED")
        invalid_arguments = (
            {},
            {"program_id": "hello_jarvis", "extra": False},
            {"path": r"D:\JarvisScripts\hello_jarvis.py"},
            {"program_id": "hello_jarvis", "argv": []},
            {"program_id": "hello_jarvis", "command": "python"},
            {"program_id": "hello_jarvis", "shell": False},
            {"program_id": "hello_jarvis", "working_directory": r"D:\JarvisScripts"},
            {"program_id": "hello_jarvis", "environment": {}},
            {"program_id": "hello_jarvis", "timeout": 1},
        )
        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    program_run(arguments, self.config)
        for program_id in ("", r"D:\hello_jarvis.py", "hello/../jarvis", "hello_jarvis;whoami", "hello jarvis", "hello\tjarvis"):
            with self.subTest(program_id=program_id):
                with self.assertRaises(ValueError):
                    program_run({"program_id": program_id}, self.config)

    def test_missing_file_is_rejected(self):
        root = Path(self.temp.name) / "JarvisScripts"
        root.mkdir()
        spec = ProgramSpec("hello_jarvis", root / "hello_jarvis.py", "test", "0" * 64, 5, 8192, 8192)
        with patch.object(programs, "PROGRAM_ROOT", root), patch.object(programs, "PROGRAM_REGISTRY", {"hello_jarvis": spec}):
            with self.assertRaises(RunnerError) as error:
                program_run({"program_id": "hello_jarvis"}, self.config)
        self.assertEqual(error.exception.code, "PROGRAM_FILE_MISSING")

    def test_hash_mismatch_is_rejected(self):
        root, spec = self._temporary_program("print('test')", expected_sha256="0" * 64)
        with patch.object(programs, "PROGRAM_ROOT", root), patch.object(programs, "PROGRAM_REGISTRY", {"hello_jarvis": spec}):
            with self.assertRaises(RunnerError) as error:
                program_run({"program_id": "hello_jarvis"}, self.config)
        self.assertEqual(error.exception.code, "PROGRAM_HASH_MISMATCH")

    def test_reparse_point_is_rejected(self):
        root, spec = self._temporary_program("print('test')")
        with patch.object(programs, "PROGRAM_ROOT", root), patch.object(programs, "PROGRAM_REGISTRY", {"hello_jarvis": spec}), patch.object(programs, "_is_reparse_point", return_value=True):
            with self.assertRaises(RunnerError) as error:
                program_run({"program_id": "hello_jarvis"}, self.config)
        self.assertEqual(error.exception.code, "PROGRAM_PATH_INVALID")

    def test_timeout_is_bounded_and_reports_timed_out(self):
        result = self._run_temporary_program("import time\ntime.sleep(2)\n", timeout_seconds=1)
        self.assertEqual(result["execution_status"], "timed_out")
        self.assertTrue(result["timed_out"])

    def test_stdout_and_stderr_are_independently_truncated(self):
        result = self._run_temporary_program("import sys\nsys.stdout.write('o' * 9000)\nsys.stderr.write('e' * 9000)\n")
        self.assertEqual(result["execution_status"], "succeeded")
        self.assertEqual(len(result["stdout"].encode("utf-8")), 8192)
        self.assertEqual(len(result["stderr"].encode("utf-8")), 8192)
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])

    def test_nonzero_exit_reports_failed(self):
        result = self._run_temporary_program("import sys\nsys.stderr.write('failure')\nsys.exit(3)\n")
        self.assertEqual(result["execution_status"], "failed")
        self.assertEqual(result["exit_code"], 3)
        self.assertFalse(result["timed_out"])

    def test_program_output_is_not_written_to_audit(self):
        result = execute_request(ActionRequest("program-audit", "program.run", {"program_id": "hello_jarvis"}, "test"), self.config)
        self.assertEqual(result.status, "success")
        record = self.config.audit_log.read_text(encoding="utf-8")
        self.assertNotIn("stdout", record)
        self.assertNotIn("stderr", record)
        self.assertNotIn("hello from jarvis", record)
        self.assertNotIn(result.output["stdout"], record)
