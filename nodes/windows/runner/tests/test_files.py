import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jarvis_runner.cli import execute_request
from jarvis_runner.config import RunnerConfig
from jarvis_runner.models import ActionRequest
from jarvis_runner import files


class FileActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "read-root"; self.root.mkdir()
        (self.root / "Report.PDF").write_text("synthetic", encoding="utf-8")
        (self.root / "README.md").write_text("synthetic", encoding="utf-8")
        (self.root / "folder").mkdir(); (self.root / "folder" / "deep.txt").write_text("synthetic", encoding="utf-8")
        self.config = RunnerConfig(workspace_root=self.root, runner_root=self.root, audit_log=self.root / "audit.jsonl", read_root=self.root)
    def tearDown(self): self.temp.cleanup()
    def invoke(self, action, arguments): return execute_request(ActionRequest("test-id", action, arguments, "test"), self.config)

    def test_list_returns_metadata_only(self):
        result = self.invoke("files.list_directory", {"path": str(self.root)})
        self.assertEqual(result.status, "success", result.error_code)
        item = next(item for item in result.output["items"] if item["name"] == "folder")
        self.assertEqual(set(item), {"name", "path", "kind", "size_bytes", "modified_at"}); self.assertIsNone(item["size_bytes"])

    def test_search_case_extension_and_kind_filters(self):
        result = self.invoke("files.search", {"path": str(self.root), "query": "report", "extensions": [".pdf"], "kind": "file"})
        self.assertEqual([item["name"] for item in result.output["items"]], ["Report.PDF"])
        directory = self.invoke("files.search", {"path": str(self.root), "query": "fold", "kind": "directory"})
        self.assertEqual(directory.output["items"][0]["kind"], "directory")
        any_kind = self.invoke("files.search", {"path": str(self.root), "query": "read", "kind": "any"})
        self.assertTrue(any_kind.output["items"])

    def test_depth_result_scan_and_output_limits(self):
        depth = self.invoke("files.search", {"path": str(self.root), "query": "deep", "max_depth": 0})
        self.assertEqual(depth.output["returned_count"], 0)
        limited = self.invoke("files.list_directory", {"path": str(self.root), "max_results": 1})
        self.assertTrue(limited.output["truncated"]); self.assertEqual(limited.output["stop_reason"], "result_limit")
        scanned = self.invoke("files.search", {"path": str(self.root), "query": "not-present", "max_scanned_entries": 1})
        self.assertEqual(scanned.output["stop_reason"], "scan_limit")
        tiny = replace(self.config, maximum_output_json_length=400)
        output = execute_request(ActionRequest("tiny", "files.list_directory", {"path": str(self.root)}, "test"), tiny)
        self.assertEqual(output.status, "success"); self.assertEqual(output.output["stop_reason"], "output_limit")

    def test_kind_wrong_json_types_and_large_result_budget_are_rejected_or_safe(self):
        for value in ([], {}, 1, True, None):
            result = self.invoke("files.search", {"path": str(self.root), "query": "report", "kind": value})
            self.assertEqual((result.status, result.error_code), ("rejected", "REQUEST_INVALID"))
        for index in range(100): (self.root / f"ordinary-{index:03}.txt").write_text("x", encoding="utf-8")
        config = replace(self.config, list_directory_max_results=100)
        result = execute_request(ActionRequest("large", "files.list_directory", {"path": str(self.root), "max_results": 100}, "test"), config)
        self.assertEqual(result.status, "success")
        self.assertIn(result.output["stop_reason"], {"result_limit", "output_limit", "completed"})

    def test_invalid_paths_and_arguments_are_rejected(self):
        cases = [{"path": "C:\\"}, {"path": "\\\\localhost\\C$"}, {"path": "relative"}, {"path": "D:relative"}, {"path": str(self.root / "Report.PDF")}, {"path": str(self.root / "missing")}]
        for arguments in cases:
            self.assertEqual(self.invoke("files.list_directory", arguments).status, "rejected")
        self.assertEqual(self.invoke("files.search", {"path": str(self.root), "query": "x", "unknown": 1}).error_code, "REQUEST_INVALID")
        self.assertEqual(self.invoke("files.search", {"path": str(self.root), "query": "x", "max_depth": True}).error_code, "REQUEST_INVALID")
        self.assertEqual(self.invoke("files.search", {"path": str(self.root), "query": "x" * 201}).error_code, "REQUEST_INVALID")
        self.assertEqual(self.invoke("files.search", {"path": str(self.root), "query": "x", "extensions": ["bad"]}).error_code, "REQUEST_INVALID")

    def test_path_error_codes_are_precise(self):
        self.assertEqual(self.invoke("files.list_directory", {"path": str(self.root / "missing")}).error_code, "PATH_NOT_FOUND")
        self.assertEqual(self.invoke("files.list_directory", {"path": str(self.root / "Report.PDF")}).error_code, "PATH_NOT_DIRECTORY")
        for path in (str(self.root) + ":stream", str(self.root / ".." / "other"), "\\\\?\\D:\\", "D:relative", str(self.root) + "-similar"):
            self.assertEqual(self.invoke("files.list_directory", {"path": path}).error_code, "PATH_NOT_ALLOWED")

    def test_nonempty_system_arguments_are_rejected(self):
        self.assertEqual(self.invoke("system.ping", {"x": 1}).error_code, "REQUEST_INVALID")
        self.assertEqual(self.invoke("system.info", {"x": 1}).error_code, "REQUEST_INVALID")

    def test_reparse_start_and_descendant_are_not_followed(self):
        outside = Path(self.temp.name) / "outside"; outside.mkdir(); (outside / "secret.txt").write_text("synthetic", encoding="utf-8")
        link = self.root / "linked"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            link.mkdir()
            with patch("jarvis_runner.security._is_reparse_point", return_value=True):
                self.assertEqual(self.invoke("files.list_directory", {"path": str(link)}).error_code, "PATH_NOT_ALLOWED")
            with patch("jarvis_runner.files._entry_reparse", side_effect=lambda entry: entry.name == "linked"):
                result = self.invoke("files.search", {"path": str(self.root), "query": "linked", "kind": "directory"})
            self.assertEqual(result.output["returned_count"], 0); self.assertGreaterEqual(result.output["skipped_reparse_points"], 1)
        else:
            self.assertEqual(self.invoke("files.list_directory", {"path": str(link)}).error_code, "PATH_NOT_ALLOWED")
            result = self.invoke("files.search", {"path": str(self.root), "query": "secret", "kind": "file"})
            self.assertEqual(result.output["returned_count"], 0); self.assertGreaterEqual(result.output["skipped_reparse_points"], 1)

    def test_time_limit_and_inaccessible_descendant(self):
        with patch("jarvis_runner.files.time.monotonic", side_effect=[0, 0, 2, 2]):
            result = self.invoke("files.list_directory", {"path": str(self.root), "timeout_ms": 1})
        self.assertEqual(result.output["stop_reason"], "time_limit")
        with patch("jarvis_runner.files.os.scandir", side_effect=[os.scandir(self.root), PermissionError()]):
            result = self.invoke("files.search", {"path": str(self.root), "query": "deep", "kind": "file"})
        self.assertEqual(result.status, "success"); self.assertEqual(result.output["skipped_inaccessible"], 1)

    def test_starting_directory_inaccessible_and_list_race_are_rejected(self):
        with patch("jarvis_runner.files.os.scandir", side_effect=PermissionError()):
            self.assertEqual(self.invoke("files.list_directory", {"path": str(self.root)}).error_code, "FILE_SCAN_FAILED")
        with patch("jarvis_runner.files._queued_directory", return_value=None), patch("jarvis_runner.files.os.scandir") as scan:
            result = self.invoke("files.list_directory", {"path": str(self.root)})
        self.assertEqual(result.error_code, "PATH_NOT_ALLOWED"); scan.assert_not_called()

    def test_ancestor_reparse_prevents_scandir(self):
        ancestor = self.root / "ancestor"; target = ancestor / "target"
        target.mkdir(parents=True)
        with patch("jarvis_runner.files._is_reparse_point", side_effect=lambda path: Path(path) == ancestor), patch("jarvis_runner.files.os.scandir") as scan:
            result = self.invoke("files.list_directory", {"path": str(target)})
        self.assertEqual(result.error_code, "PATH_NOT_ALLOWED"); scan.assert_not_called()

    def test_entry_stat_permission_error_skips_before_item(self):
        class Entry:
            name = "blocked"; path = "blocked"
            def is_symlink(self): return False
            def stat(self, *, follow_symlinks): raise PermissionError()
        class Scan:
            def __enter__(self): return iter([Entry()])
            def __exit__(self, *args): return False
        with patch("jarvis_runner.files.os.scandir", return_value=Scan()), patch("jarvis_runner.files._item") as item:
            result = self.invoke("files.list_directory", {"path": str(self.root)})
        item.assert_not_called(); self.assertEqual(result.output["skipped_inaccessible"], 1)

    def test_queued_directory_reparse_is_not_scanned(self):
        original_scandir = os.scandir; calls = []
        def tracking_scandir(path): calls.append(Path(path)); return original_scandir(path)
        with patch("jarvis_runner.files._queued_directory", side_effect=[self.root, None]), patch("jarvis_runner.files.os.scandir", side_effect=tracking_scandir):
            result = self.invoke("files.search", {"path": str(self.root), "query": "deep", "kind": "file"})
        self.assertEqual(result.status, "success"); self.assertGreaterEqual(result.output["skipped_reparse_points"], 1)
        self.assertNotIn(self.root / "folder", calls)

    def test_production_d_search_uses_fixed_everything_backend_and_bounds_results(self):
        config = replace(self.config, read_root=Path(r"D:\\"), search_max_results=50)
        item = {"name": "数字IC书单与学习路线规划.pdf", "path": r"D:\\Books\\数字IC书单与学习路线规划.pdf", "kind": "file", "size_bytes": 1, "modified_at": "2026-01-01T00:00:00+00:00"}
        completed = subprocess.CompletedProcess([], 0, item["path"] + "\n", "")
        with patch("jarvis_runner.files.EVERYTHING_EXECUTABLE_PATH", Path(os.__file__)), patch("jarvis_runner.files.subprocess.run", return_value=completed) as run, patch("jarvis_runner.files._everything_item", return_value=item):
            result = execute_request(ActionRequest("d-drive", "files.search", {"path": r"D:\\", "query": "数字IC书单与学习路线规划", "max_results": 50}, "test"), config)
        self.assertEqual(result.status, "success", result.error_code)
        self.assertEqual(result.output["items"], [item])
        self.assertEqual(run.call_args.args[0][1:5], ["-n", "20", "-s", "-full-path-and-name"])
        self.assertEqual(run.call_args.args[0][-1], "数字ic书单与学习路线规划")
        self.assertEqual(run.call_args.kwargs["cwd"], "D:\\")
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_everything_result_path_cannot_escape_d(self):
        config = replace(self.config, read_root=Path(r"D:\\"))
        self.assertIsNone(files._everything_item(r"C:\\Windows\\notepad.exe", Path(r"D:\\"), config))

    def test_everything_result_stays_within_requested_d_subtree(self):
        config = replace(self.config, read_root=Path(r"D:\\"))
        self.assertIsNone(files._everything_item(r"D:\\$RECYCLE.BIN\\README.md", Path(r"D:\\JarvisWorkspace\\JarvisRunner"), config))

    def test_production_d_search_rejects_c_and_reports_missing_everything(self):
        config = replace(self.config, read_root=Path(r"D:\\"))
        rejected = execute_request(ActionRequest("c-drive", "files.search", {"path": r"C:\\", "query": "hosts"}, "test"), config)
        self.assertEqual((rejected.status, rejected.error_code), ("rejected", "PATH_NOT_ALLOWED"))
        with patch("jarvis_runner.files.EVERYTHING_EXECUTABLE_PATH", None):
            unavailable = execute_request(ActionRequest("d-drive", "files.search", {"path": r"D:\\", "query": "book"}, "test"), config)
        self.assertEqual((unavailable.status, unavailable.error_code), ("rejected", "EVERYTHING_UNAVAILABLE"))
