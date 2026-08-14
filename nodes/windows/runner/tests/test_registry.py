import unittest

from jarvis_runner.registry import get_action, registered_actions


class RegistryTests(unittest.TestCase):
    def test_only_seven_actions_are_registered(self): self.assertEqual(set(registered_actions()), {"system.ping", "system.info", "system.status", "files.list_directory", "files.search", "program.list", "program.run"})
    def test_unknown_action_is_absent(self): self.assertIsNone(get_action("cmd.execute"))
