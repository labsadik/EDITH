"""Home Assistant status failures must be actionable and must never traceback."""
import json
import unittest
from unittest.mock import patch

from agents import smart_network


class HomeAssistantSetupTests(unittest.TestCase):
    def test_status_without_pairing_is_a_structured_setup_state(self):
        with (
            patch.object(smart_network, "_ha_credentials", return_value=None),
            patch.object(smart_network, "_ha_request") as request,
        ):
            result = json.loads(smart_network.run_smart_network("status"))
        self.assertFalse(result["ok"])
        self.assertFalse(result["connected"])
        self.assertTrue(result["needs_pairing"])
        self.assertIn("configure_home_assistant.py", result["setup"])
        request.assert_not_called()

    def test_read_or_control_without_pairing_never_attempts_http(self):
        for action, entity, service in (
            ("read", "light.living_room", ""),
            ("control", "light.living_room", "light.turn_on"),
        ):
            with (
                self.subTest(action=action),
                patch.object(smart_network, "_ha_credentials", return_value=None),
                patch.object(smart_network, "_ha_request") as request,
            ):
                result = json.loads(smart_network.run_smart_network(action, entity, service, {}))
                self.assertFalse(result["ok"])
                self.assertTrue(result["needs_pairing"])
                request.assert_not_called()

    def test_unreachable_or_invalid_home_assistant_returns_actionable_result(self):
        with (
            patch.object(smart_network, "_ha_credentials", return_value=("http://ha.local:8123", "token")),
            patch.object(smart_network, "_ha_request", side_effect=RuntimeError("Home Assistant is paired but unreachable")),
        ):
            result = json.loads(smart_network.run_smart_network("status"))
        self.assertFalse(result["ok"])
        self.assertTrue(result["paired"])
        self.assertIn("unreachable", result["error"])


if __name__ == "__main__":
    unittest.main()
