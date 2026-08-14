import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jarvis_runner import cli
from jarvis_runner.errors import RunnerError


class ServeTailscaleTests(unittest.TestCase):
    def _failure(self, error):
        with (
            patch("jarvis_runner.cli.load_config", return_value=SimpleNamespace(auth_key_path="unused", maximum_argument_string_length=1000)),
            patch("jarvis_runner.cli.append_runner_started_audit"),
            patch("jarvis_runner.cli.validate_network_config"),
            patch("jarvis_runner.cli.load_auth_key", side_effect=error),
            patch("builtins.print") as output,
        ):
            self.assertEqual(cli.main(["serve-tailscale"]), 1)
        return json.loads(output.call_args.args[0])

    def test_serve_failure_records_only_safe_exception_details(self):
        with self.subTest("os_error"):
            body = self._failure(OSError("unsafe detail"))
            self.assertEqual(body["failure_stage"], "auth_key")
            self.assertEqual(body["underlying_exception_class"], "OSError")
            self.assertIsNone(body["underlying_error_code"])
            self.assertNotIn("unsafe detail", json.dumps(body))
        with self.subTest("runner_error"):
            body = self._failure(RunnerError("AUTH_KEY_UNAVAILABLE", "unsafe detail"))
            self.assertEqual(body["underlying_error_code"], "AUTH_KEY_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
