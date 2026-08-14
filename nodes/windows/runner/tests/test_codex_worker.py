import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.agent_staging import AgentStaging
from jarvis_runner.authority import AdmissionError
from jarvis_runner.codex_worker import (
    CODEX_AUTH_HOME, CODEX_BACKEND_ID, CodexTaskRequest, CodexWorkerService,
    _codex_arguments_allowed, _codex_environment,
)
from jarvis_runner.config import RunnerConfig
from jarvis_runner.errors import RunnerError
from jarvis_runner.jobs import JobStore
from jarvis_runner.models import JobResult
from jarvis_runner.process_supervisor import ProcessSupervisor, ProcessSupervisorError
from jarvis_runner.task_authorization import TaskAuthorizationStore


class _FakeSupervisor:
    def __init__(self, store):
        self.store = store
        self.started = []
        self.status = "succeeded"
        self.mutate = None
        self.write_final_message = True
        self.start_error = None

    def start(self, job_id, request, completion_hook=None):
        self.started.append(request)
        if self.start_error is not None:
            raise self.start_error
        self.store.transition(job_id, "running")
        if self.mutate is not None:
            self.mutate(Path(request.cwd))
        if self.status == "succeeded" and self.write_final_message:
            output_index = request.argv.index("--output-last-message") + 1
            Path(request.argv[output_index]).write_text("Codex completed the assigned task.", encoding="utf-8")
        error_code = None if self.status == "succeeded" else self.status.upper()
        exit_code = 0 if self.status == "succeeded" else 1
        result = JobResult(self.status, "fake process result", exit_code=exit_code, error_code=error_code)
        if completion_hook is not None:
            result = completion_hook(job_id, result)
        self.store.transition(job_id, result.status, error_code=result.error_code, error_summary=result.summary)
        self.store.set_result(job_id, result)

    def cancel(self, job_id):
        del job_id


class CodexWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        runner_root = root / "JarvisWorkspace" / "JarvisRunner"
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        self.config = RunnerConfig(
            workspace_root=runner_root.parent, runner_root=runner_root,
            audit_log=runner_root / "logs" / "audit.jsonl",
            job_state_path=runner_root / "state" / "jobs.json",
            read_root=root, process_timeout_min_seconds=1, process_timeout_max_seconds=60,
        )
        self.authorizations = TaskAuthorizationStore(self.config)
        self.store = JobStore(self.config)
        self.fake = _FakeSupervisor(self.store)
        self.service = CodexWorkerService(
            self.config, self.authorizations, store=self.store,
            staging=AgentStaging(self.config), supervisor=self.fake,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _authorization(self, *, subject="autumn:user", adapter="codex", workspace=None, task="update files"):
        request = self.authorizations.create_request(
            subject=subject, adapter=adapter, real_workspace=workspace or self.workspace,
            task_summary=task, network_policy="none",
        )
        self.authorizations.approve(request.authorization_request_id, subject=subject)
        return request.authorization_request_id

    def _request(self, authorization_request_id, *, subject="autumn:user", task="update files", workspace=None):
        return CodexTaskRequest(subject, task, workspace or self.workspace, 10, authorization_request_id)

    def test_unapproved_or_wrong_subject_does_not_start_codex(self):
        pending = self.authorizations.create_request(
            subject="autumn:user", adapter="codex", real_workspace=self.workspace,
            task_summary="update files", network_policy="none",
        )
        with self.assertRaises(RunnerError) as caught:
            self.service.submit(self._request(pending.authorization_request_id))
        self.assertEqual(caught.exception.code, "AUTHORIZATION_NOT_APPROVED")

        approved = self._authorization(subject="autumn:owner")
        with self.assertRaises(RunnerError) as caught:
            self.service.submit(self._request(approved, subject="autumn:other"))
        self.assertEqual(caught.exception.code, "AUTHORIZATION_SUBJECT_MISMATCH")
        self.assertEqual(self.fake.started, [])

    def test_task_or_workspace_scope_mismatch_does_not_start_codex(self):
        wrong_task = self._authorization(task="expected task")
        with self.assertRaises(RunnerError) as caught:
            self.service.submit(self._request(wrong_task, task="different task"))
        self.assertEqual(caught.exception.code, "AUTHORIZATION_SCOPE_MISMATCH")

        other_workspace = self.workspace.parent / "other-workspace"
        other_workspace.mkdir()
        wrong_workspace = self._authorization(workspace=self.workspace)
        with self.assertRaises(RunnerError) as caught:
            self.service.submit(self._request(wrong_workspace, workspace=other_workspace))
        self.assertEqual(caught.exception.code, "AUTHORIZATION_SCOPE_MISMATCH")
        self.assertEqual(self.fake.started, [])

    def test_cwd_and_invocation_are_runner_fixed_and_inputs_cannot_inject(self):
        record = self.service.submit(self._request(self._authorization()))
        invocation = self.fake.started[0]
        self.assertEqual(record.status, "succeeded")
        self.assertEqual(invocation.executable_id, CODEX_BACKEND_ID)
        self.assertNotEqual(invocation.cwd, self.workspace)
        self.assertEqual(Path(invocation.cwd).name, "work")
        self.assertIn("--ignore-user-config", invocation.argv)
        self.assertIn("--ephemeral", invocation.argv)
        self.assertIn("workspace-write", invocation.argv)
        self.assertNotIn("--add-dir", invocation.argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", invocation.argv)
        with self.assertRaises(TypeError):
            CodexTaskRequest(
                subject="autumn:user", task="x", real_workspace=self.workspace, timeout=10,
                authorization_request_id="id", executable="python",
            )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "not-forwarded", "CALLER_ENV": "not-forwarded"}):
            environment = _codex_environment()
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CALLER_ENV", environment)
        self.assertEqual(environment["CODEX_HOME"], str(CODEX_AUTH_HOME))
        staging_root = (self.config.runner_root.parent / "AgentStaging").resolve()
        self.assertTrue(_codex_arguments_allowed(invocation.argv, staging_root))
        injected = list(invocation.argv)
        injected[injected.index("--json")] = "--add-dir"
        self.assertFalse(_codex_arguments_allowed(tuple(injected), staging_root))

    def test_real_supervisor_admission_reaches_popen_with_fixed_contract(self):
        """Exercise the real admission path while preventing any Codex process start."""
        service = CodexWorkerService(
            self.config, self.authorizations, store=self.store,
            staging=AgentStaging(self.config),
        )
        self.assertIsInstance(service.supervisor, ProcessSupervisor)

        with patch("jarvis_runner.process_supervisor.subprocess.Popen", side_effect=OSError("test boundary")) as popen:
            record = service.submit(self._request(self._authorization()))

        self.assertEqual(popen.call_count, 1)
        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(command[0], str(service.supervisor._catalog[CODEX_BACKEND_ID].executable_path))
        self.assertTrue(_codex_arguments_allowed(tuple(command[1:]), self.config.runner_root.parent / "AgentStaging"))
        self.assertEqual(Path(options["cwd"]).name, "work")
        self.assertEqual(options["env"], _codex_environment())
        self.assertFalse(options["shell"])
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.error_code, "PROCESS_START_FAILED")
        self.assertFalse((self.workspace / "created-by-codex.txt").exists())

    def test_production_multiline_task_reaches_popen_with_fixed_contract(self):
        """The production task must fit the fixed policy prompt without starting Codex."""
        task = (
            "Open smoke.txt in the provided workspace.\n"
            "Change only the line:\n\n"
            "STATE=BEFORE\n\n"
            "to:\n\n"
            "STATE=AFTER\n\n"
            "Do not change any other content.\n"
            "Do not create, delete, rename, move, or access unrelated files.\n"
            "Do not access files outside the provided staging workspace."
        )
        service = CodexWorkerService(
            self.config, self.authorizations, store=self.store,
            staging=AgentStaging(self.config),
        )
        with patch("jarvis_runner.process_supervisor.subprocess.Popen", side_effect=OSError("test boundary")) as popen:
            record = service.submit(self._request(self._authorization(task=task), task=task))
        self.assertEqual(popen.call_count, 1)
        argv = tuple(popen.call_args.args[0][1:])
        self.assertGreater(len(argv[-1]), self.config.maximum_argument_string_length)
        self.assertTrue(_codex_arguments_allowed(argv, self.config.runner_root.parent / "AgentStaging"))
        self.assertEqual(record.error_code, "PROCESS_START_FAILED")

    def test_start_rejection_audit_records_safe_admission_details_and_terminal_job(self):
        self.fake.start_error = AdmissionError("PROCESS_POLICY_MISMATCH", "prompt must not be logged")
        with self.assertRaises(RunnerError) as caught:
            self.service.submit(self._request(self._authorization()))
        self.assertEqual(caught.exception.code, "CODEX_START_REJECTED")
        job = caught.exception.job
        self.assertEqual((job.status, job.error_code), ("cancelled", "CODEX_START_REJECTED"))
        row = json.loads(self.config.audit_log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(row["job_id"], job.job_id)
        self.assertEqual(row["error_code"], "CODEX_START_REJECTED")
        self.assertEqual(row["underlying_exception_class"], "AdmissionError")
        self.assertEqual(row["underlying_error_code"], "PROCESS_POLICY_MISMATCH")
        self.assertEqual(row["safe_message"], "Codex worker could not be started")
        self.assertNotIn("prompt must not be logged", self.config.audit_log.read_text(encoding="utf-8"))

    def test_start_rejection_audit_records_process_supervisor_class(self):
        self.fake.start_error = ProcessSupervisorError("internal startup detail")
        with self.assertRaises(RunnerError) as caught:
            self.service.submit(self._request(self._authorization()))
        job = caught.exception.job
        row = json.loads(self.config.audit_log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual((row["job_id"], row["error_code"]), (job.job_id, "CODEX_START_REJECTED"))
        self.assertEqual(row["underlying_exception_class"], "ProcessSupervisorError")
        self.assertIsNone(row["underlying_error_code"])

    def test_success_publishes_create_and_modify(self):
        (self.workspace / "existing.txt").write_text("base", encoding="utf-8")

        def mutate(work):
            (work / "existing.txt").write_text("modified", encoding="utf-8")
            (work / "created.txt").write_text("created", encoding="utf-8")

        self.fake.mutate = mutate
        record = self.service.submit(self._request(self._authorization()))
        self.assertEqual(record.status, "succeeded")
        self.assertEqual((self.workspace / "existing.txt").read_text(encoding="utf-8"), "modified")
        self.assertEqual((self.workspace / "created.txt").read_text(encoding="utf-8"), "created")
        self.assertEqual(record.result.metadata["published_create_count"], 1)
        self.assertEqual(record.result.metadata["published_modify_count"], 1)
        self.assertEqual(record.result.stdout, "")

    def test_failure_timeout_and_cancel_never_publish(self):
        for status in ("failed", "timed_out", "cancelled"):
            with self.subTest(status=status):
                target = self.workspace / f"{status}.txt"
                self.fake.status = status
                self.fake.mutate = lambda work, name=target.name: (work / name).write_text("agent", encoding="utf-8")
                record = self.service.submit(self._request(self._authorization(task=f"task {status}"), task=f"task {status}"))
                self.assertEqual(record.status, status)
                self.assertFalse(target.exists())
                self.assertEqual(record.result.stdout, "")
                self.assertEqual(record.result.stderr, "")

    def test_success_without_usable_result_never_publishes(self):
        self.fake.status = "succeeded"
        self.fake.write_final_message = False
        self.fake.mutate = lambda work: (work / "unpublished.txt").write_text("agent", encoding="utf-8")
        record = self.service.submit(self._request(self._authorization()))
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.result.error_code, "CODEX_RESULT_INVALID")
        self.assertFalse((self.workspace / "unpublished.txt").exists())

    def test_delete_producing_work_is_denied_and_real_file_remains(self):
        target = self.workspace / "keep.txt"
        target.write_text("keep", encoding="utf-8")
        self.fake.mutate = lambda work: (work / "keep.txt").unlink()
        record = self.service.submit(self._request(self._authorization()))
        self.assertEqual(record.status, "failed")
        self.assertEqual(record.result.error_code, "PUBLISH_DENIED")
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_python_and_node_authorizations_cannot_use_codex_adapter(self):
        for adapter in ("python", "node"):
            with self.subTest(adapter=adapter):
                authorization = self._authorization(adapter=adapter, task=f"{adapter} task")
                with self.assertRaises(RunnerError) as caught:
                    self.service.submit(self._request(authorization, task=f"{adapter} task"))
                self.assertEqual(caught.exception.code, "AUTHORIZATION_SCOPE_MISMATCH")
        self.assertEqual(self.fake.started, [])


if __name__ == "__main__":
    unittest.main()
