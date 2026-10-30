"""Home Assistant status failures must be actionable and must never traceback."""
import json
import unittest
from unittest.mock import patch

from agents import smart_network


class HomeAssistantSetupTests(unittest.TestCase):
    def test_valid_home_assistant_credentials_are_verified_without_persisting(self):
        response = type("Response", (), {
            "status_code": 200,
            "json": lambda self: {"location_name": "Home"},
            "raise_for_status": lambda self: None,
        })()
        with patch.object(smart_network.requests, "get", return_value=response) as get:
            result = smart_network.test_home_assistant_connection(
                "http://ha.local:8123/", "token-secret"
            )
        self.assertTrue(result["ok"])
        args, kwargs = get.call_args
        self.assertEqual(args[0], "http://ha.local:8123/api/config")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-secret")
        self.assertFalse(kwargs.get("allow_redirects", True) is True)

    def test_invalid_home_assistant_token_is_rejected_before_pairing(self):
        response = type("Response", (), {"status_code": 401})()
        with patch.object(smart_network.requests, "get", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "rejected this token"):
                smart_network.test_home_assistant_connection(
                    "http://ha.local:8123", "bad-token"
                )

    def test_home_assistant_redirect_is_not_followed_silently(self):
        response = type("Response", (), {"status_code": 302})()
        with patch.object(smart_network.requests, "get", return_value=response) as get:
            with self.assertRaisesRegex(RuntimeError, "redirected"):
                smart_network.test_home_assistant_connection(
                    "http://ha.local:8123", "token"
                )
            self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_home_assistant_url_with_embedded_credentials_is_rejected(self):
        with self.assertRaises(ValueError):
            smart_network.test_home_assistant_connection(
                "http://user:pass@ha.local:8123", "token"
            )

    def test_pair_home_assistant_verifies_before_saving(self):
        with (
            patch.object(smart_network, "test_home_assistant_connection",
                         return_value={"ok": True, "connected": True}) as verify,
            patch.object(smart_network, "configure_home_assistant",
                         return_value={"saved": True, "token_storage": "keyring"}) as save,
        ):
            result = smart_network.pair_home_assistant(
                "http://ha.local:8123", "secret-token"
            )
        verify.assert_called_once_with("http://ha.local:8123", "secret-token", timeout=5.0)
        save.assert_called_once_with("http://ha.local:8123", "secret-token")
        self.assertTrue(result["verified"])
        self.assertEqual(result["token_storage"], "keyring")

    def test_pair_home_assistant_does_not_save_rejected_credentials(self):
        with (
            patch.object(smart_network, "test_home_assistant_connection",
                         side_effect=RuntimeError("Home Assistant rejected this token")),
            patch.object(smart_network, "configure_home_assistant") as save,
        ):
            with self.assertRaisesRegex(RuntimeError, "rejected this token"):
                smart_network.pair_home_assistant(
                    "http://ha.local:8123", "bad-token"
                )
        save.assert_not_called()

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
