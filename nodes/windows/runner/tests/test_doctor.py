import tempfile
import unittest
from pathlib import Path

from jarvis_runner.cli import filter_doctor_findings, scan_source_for_dangerous_calls


class DoctorTests(unittest.TestCase):
    def test_ast_detects_dangerous_constructs(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "bad.py"
            source.write_text("import subprocess as sp\nfrom subprocess import run\nimport os as operating\noperating.system('x')\nshell = True\neval('x')\nexec('x')\n", encoding="utf-8")
            rules = {item["rule"] for item in scan_source_for_dangerous_calls(Path(temp))}
            self.assertTrue({"import_subprocess", "from_subprocess_import", "os_system_call", "shell_true_assignment", "dynamic_builtin_call"}.issubset(rules))
    def test_safe_file_does_not_trigger(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "safe.py").write_text("import json\nvalue = {'ok': True}\n", encoding="utf-8")
            self.assertEqual(scan_source_for_dangerous_calls(Path(temp)), [])

    def test_doctor_only_allows_fixed_process_boundary_subprocess_findings(self):
        findings = [
            {"file": "programs.py", "line": 1, "rule": "import_subprocess"},
            {"file": "programs.py", "line": 2, "rule": "subprocess_popen_call"},
            {"file": "programs.py", "line": 3, "rule": "import_hashlib"},
            {"file": "other.py", "line": 4, "rule": "import_subprocess"},
            {"file": "programs.py", "line": 5, "rule": "subprocess_call"},
            {"file": "process_supervisor.py", "line": 6, "rule": "import_subprocess"},
            {"file": "process_supervisor.py", "line": 7, "rule": "subprocess_popen_call"},
            {"file": "process_supervisor.py", "line": 8, "rule": "subprocess_call"},
            {"file": "files.py", "line": 9, "rule": "import_subprocess"},
            {"file": "files.py", "line": 10, "rule": "subprocess_call"},
            {"file": "files.py", "line": 11, "rule": "subprocess_popen_call"},
        ]
        self.assertEqual(filter_doctor_findings(findings), [findings[3], findings[4], findings[10]])
