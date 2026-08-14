import sys
import tempfile
import unittest
from pathlib import Path

from jarvis_runner.authority import (
    AdmissionError, AuthorityLevel, ExecutablePolicy, PRODUCTION_EXECUTABLE_CATALOG,
    ProcessRequest, approve_process_request,
)
from jarvis_runner.config import RunnerConfig
from jarvis_runner.models import ProcessJobSpec


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.config = RunnerConfig(workspace_root=root, runner_root=root / "JarvisRunner", audit_log=root / "JarvisRunner" / "logs" / "audit.jsonl")
        self.cwd = Path(__file__).parent

    def tearDown(self):
        self.temp.cleanup()

    def _policy(self, **changes):
        values = dict(executable_id="probe", executable_path=Path(sys.executable), cwd=self.cwd, argument_validator=lambda argv: argv == ("success",), test_only=True)
        values.update(changes)
        return ExecutablePolicy(**values)

    def _request(self, **changes):
        values = dict(executable_id="probe", argv=("success",), cwd=self.cwd, timeout_seconds=1)
        values.update(changes)
        return ProcessRequest(**values)

    def test_caller_authority_hint_cannot_lower_runner_requirement(self):
        policy = self._policy(write_scope="workspace")
        request = self._request(write_scope="workspace", requested_authority=AuthorityLevel.L1_READ_OPEN)
        with self.assertRaisesRegex(AdmissionError, "not enabled"):
            approve_process_request(request, {"probe": policy}, self.config)

    def test_external_admin_and_delete_are_denied(self):
        cases = (
            (self._policy(network_policy="allowed"), self._request(network_policy="allowed"), "not enabled"),
            (self._policy(operation_type="system_admin"), self._request(operation_type="system_admin"), "denied"),
            (self._policy(operation_type="delete"), self._request(operation_type="delete"), "hard denied"),
        )
        for policy, request, expected in cases:
            with self.subTest(policy=policy.operation_type):
                with self.assertRaisesRegex(AdmissionError, expected):
                    approve_process_request(request, {"probe": policy}, self.config)

    def test_raw_command_and_policy_mismatch_are_rejected(self):
        policy = self._policy()
        with self.assertRaisesRegex(AdmissionError, "structured list"):
            approve_process_request(self._request(argv="python worker_probe.py"), {"probe": policy}, self.config)
        with self.assertRaisesRegex(AdmissionError, "must match"):
            approve_process_request(self._request(network_policy="allowed"), {"probe": policy}, self.config)

    def test_runner_policy_resolves_paths_and_catalog_profiles_are_declarative(self):
        spec = approve_process_request(self._request(), {"probe": self._policy()}, self.config)
        self.assertEqual(spec.executable_path, Path(sys.executable).resolve(strict=False))
        self.assertEqual(set(PRODUCTION_EXECUTABLE_CATALOG), {"7zip", "git", "python", "node", "everything"})
        self.assertEqual(PRODUCTION_EXECUTABLE_CATALOG["7zip"].policy_class, "archive")
        self.assertEqual(PRODUCTION_EXECUTABLE_CATALOG["git"].policy_class, "git")
        self.assertEqual(PRODUCTION_EXECUTABLE_CATALOG["python"].policy_class, "build_or_script_runtime")
        self.assertEqual(PRODUCTION_EXECUTABLE_CATALOG["node"].policy_class, "build_or_script_runtime")

    def _production_spec(self, executable, arguments, **changes):
        values = dict(
            type="process", executable=executable, arguments=tuple(arguments), cwd=Path(r"D:\JarvisWorkspace\JarvisRunner"),
            timeout=10, write_scope="none", network_policy="none",
        )
        values.update(changes)
        return ProcessJobSpec(**values)

    def test_git_authority_classification(self):
        catalog = PRODUCTION_EXECUTABLE_CATALOG
        for command in ("status", "diff", "log", "show", "rev-parse"):
            approved = approve_process_request(self._production_spec("git", [command]), catalog, self.config)
            self.assertEqual(approved.required_authority, AuthorityLevel.L1_READ_OPEN)
            self.assertEqual(approved.argv[0], "--no-pager")
            if command in {"diff", "log", "show"}:
                self.assertIn("--no-ext-diff", approved.argv)
                self.assertIn("--no-textconv", approved.argv)
        for command in ("add", "commit", "checkout", "switch", "restore"):
            with self.subTest(command=command), self.assertRaises(AdmissionError) as caught:
                approve_process_request(self._production_spec("git", [command]), catalog, self.config)
            self.assertEqual(caught.exception.code, "AUTHORIZATION_REQUIRED")
        for command in ("push", "pull", "fetch", "clone"):
            with self.subTest(command=command), self.assertRaises(AdmissionError) as caught:
                approve_process_request(self._production_spec("git", [command]), catalog, self.config)
            self.assertEqual(caught.exception.code, "AUTHORIZATION_REQUIRED")
        for arguments in (("clean", "-fd"), ("reset", "--hard", "HEAD")):
            with self.subTest(arguments=arguments), self.assertRaises(AdmissionError) as caught:
                approve_process_request(self._production_spec("git", arguments), catalog, self.config)
            self.assertEqual(caught.exception.code, "DENY")
        for arguments in (("diff", "--output=result.txt"), ("show", "--ext-diff"), ("log", "--textconv")):
            with self.subTest(arguments=arguments), self.assertRaises(AdmissionError) as caught:
                approve_process_request(self._production_spec("git", arguments), catalog, self.config)
            self.assertEqual(caught.exception.code, "DENY")

    def test_python_node_cannot_be_lowered_and_everything_availability_is_explicit(self):
        for executable in ("python", "node"):
            with self.subTest(executable=executable), self.assertRaises(AdmissionError) as caught:
                approve_process_request(self._production_spec(executable, ["--version"]), PRODUCTION_EXECUTABLE_CATALOG, self.config)
            self.assertEqual(caught.exception.code, "AUTHORIZATION_REQUIRED")
        everything = PRODUCTION_EXECUTABLE_CATALOG["everything"]
        if everything.executable_path is None:
            with self.assertRaises(AdmissionError) as caught:
                approve_process_request(self._production_spec("everything", ["README"]), PRODUCTION_EXECUTABLE_CATALOG, self.config)
            self.assertEqual(caught.exception.code, "EXECUTABLE_UNAVAILABLE")
        else:
            with self.assertRaises(AdmissionError) as caught:
                approve_process_request(self._production_spec("everything", ["README"]), PRODUCTION_EXECUTABLE_CATALOG, self.config)
            self.assertEqual(caught.exception.code, "ARGUMENTS_NOT_ALLOWED")
