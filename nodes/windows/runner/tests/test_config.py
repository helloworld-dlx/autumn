import json
import tempfile
import unittest
from pathlib import Path

from jarvis_runner.config import (
    AUDIT_BACKUP_COUNT_HARD_LIMIT,
    AUDIT_MAX_BYTES_CONFIG_MINIMUM,
    AUDIT_MAX_BYTES_HARD_LIMIT,
    DEFAULT_AUDIT_BACKUP_COUNT,
    DEFAULT_AUDIT_MAX_BYTES,
    PRODUCTION_WORKSPACE_ROOT,
    load_config,
)


class ConfigTests(unittest.TestCase):
    def _load(self, workspace_root: str):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); (base / "config").mkdir()
            (base / "config" / "runner.json").write_text(json.dumps({"workspace_root": workspace_root, "runner_root": r"D:\\JarvisWorkspace\\JarvisRunner", "audit_log": r"D:\\JarvisWorkspace\\JarvisRunner\\logs\\audit.jsonl"}), encoding="utf-8")
            return load_config(base)
    def test_c_drive_override_is_rejected(self):
        with self.assertRaises(ValueError): self._load(r"C:\\")
    def test_prefix_workspace_override_is_rejected(self):
        with self.assertRaises(ValueError): self._load(r"D:\\JarvisWorkspace2")
    def test_fixed_workspace_is_allowed(self):
        self.assertEqual(self._load(str(PRODUCTION_WORKSPACE_ROOT)).workspace_root, PRODUCTION_WORKSPACE_ROOT)

    def test_audit_defaults_are_loaded(self):
        config = self._load(str(PRODUCTION_WORKSPACE_ROOT))
        self.assertEqual(config.audit_max_bytes, DEFAULT_AUDIT_MAX_BYTES)
        self.assertEqual(config.audit_backup_count, DEFAULT_AUDIT_BACKUP_COUNT)

    def test_runner_example_contains_audit_settings(self):
        example_path = Path(__file__).parents[1] / "config" / "runner.example.json"
        example = json.loads(example_path.read_text(encoding="utf-8"))
        self.assertEqual(example["audit_max_bytes"], DEFAULT_AUDIT_MAX_BYTES)
        self.assertEqual(example["audit_backup_count"], DEFAULT_AUDIT_BACKUP_COUNT)

    def test_audit_limits_reject_invalid_values(self):
        for value in (0, -1, True, "4096", AUDIT_MAX_BYTES_HARD_LIMIT + 1, AUDIT_MAX_BYTES_CONFIG_MINIMUM - 1):
            with self.assertRaises(ValueError):
                self._load_with({"audit_max_bytes": value})
        for value in (0, -1, False, "3", AUDIT_BACKUP_COUNT_HARD_LIMIT + 1):
            with self.assertRaises(ValueError):
                self._load_with({"audit_backup_count": value})

    def test_audit_limits_accept_valid_boundaries(self):
        lower = self._load_with({"audit_max_bytes": AUDIT_MAX_BYTES_CONFIG_MINIMUM, "audit_backup_count": 1})
        upper = self._load_with({"audit_max_bytes": AUDIT_MAX_BYTES_HARD_LIMIT, "audit_backup_count": AUDIT_BACKUP_COUNT_HARD_LIMIT})
        self.assertEqual(lower.audit_max_bytes, AUDIT_MAX_BYTES_CONFIG_MINIMUM)
        self.assertEqual(lower.audit_backup_count, 1)
        self.assertEqual(upper.audit_max_bytes, AUDIT_MAX_BYTES_HARD_LIMIT)
        self.assertEqual(upper.audit_backup_count, AUDIT_BACKUP_COUNT_HARD_LIMIT)

    def test_read_root_and_hard_limit_overrides_are_rejected(self):
        for read_root in (r"C:\\", r"\\server\\share", r"\\?\\D:\\"):
            with self.assertRaises(ValueError): self._load(str(PRODUCTION_WORKSPACE_ROOT)) if read_root == str(PRODUCTION_WORKSPACE_ROOT) else self._load_with({"read_root": read_root})
        with self.assertRaises(ValueError): self._load_with({"list_directory_max_results": 101})
        with self.assertRaises(ValueError): self._load_with({"maximum_output_json_length": 1})

    def test_minimum_output_budget_uses_production_validation_rules(self):
        with self.assertRaises(ValueError): self._load_with({"maximum_output_nodes": 20})
        self.assertEqual(self._load_with({"maximum_output_nodes": 21}).maximum_output_nodes, 21)
        with self.assertRaises(ValueError): self._load_with({"maximum_output_string_length": 1})
        with self.assertRaises(ValueError): self._load_with({"maximum_output_json_length": 1})

    def _load_with(self, extra):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); (base / "config").mkdir()
            values = {"workspace_root": str(PRODUCTION_WORKSPACE_ROOT), "runner_root": r"D:\\JarvisWorkspace\\JarvisRunner", "audit_log": r"D:\\JarvisWorkspace\\JarvisRunner\\logs\\audit.jsonl"}; values.update(extra)
            (base / "config" / "runner.json").write_text(json.dumps(values), encoding="utf-8")
            return load_config(base)
