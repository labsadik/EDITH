"""Authenticated Home Assistant write-control guardrail tests."""
import json
import unittest
from unittest.mock import patch

from agents import smart_network
from core.action_guard import confirmation_requirement
from edith.platform.permissions import tool_tier


class SmartNetworkHomeAssistantTests(unittest.TestCase):
    def test_paired_light_service_control_calls_authenticated_adapter(self):
        state = {"entity_id": "light.living_room", "state": "off", "attributes": {}}
        with (
            patch.object(smart_network, "_ha_credentials", return_value=("http://ha.local:8123", "test-token")),
            patch.object(smart_network, "_ha_request", side_effect=[state, [{"entity_id": "light.living_room"}]]) as request,
        ):
            result = json.loads(smart_network.run_smart_network(
                "control", "light.living_room", "light.turn_on", {"brightness_pct": 60}
            ))
        self.assertTrue(result["ok"])
        self.assertEqual(result["service"], "light.turn_on")
        self.assertEqual(request.call_args.args, ("POST", "services/light/turn_on"))

    def test_smart_home_write_is_tier_two_and_requires_confirmation(self):
        args = {"action": "control", "entity_id": "switch.fan", "service": "switch.turn_off"}
        self.assertEqual(tool_tier("smart_network", args), 2)
        prompt = confirmation_requirement("smart_network", args)
        self.assertTrue(prompt)
        self.assertIn("switch.fan", prompt)
        self.assertIn("switch.turn_off", prompt)

    def test_unapproved_service_is_rejected_before_any_http_call(self):
        with patch.object(smart_network, "_ha_request") as request:
            with self.assertRaises(ValueError):
                smart_network.run_smart_network(
                    "control", "light.living_room", "shell.execute", {}
                )
        request.assert_not_called()

    def test_discovery_works_without_home_assistant_pairing(self):
        with (
            patch.object(smart_network, "_neighbors", return_value=([], "ip")),
            patch.object(smart_network, "_interfaces", return_value={}),
            patch.object(smart_network, "_ha_credentials", return_value=None),
        ):
            result = json.loads(smart_network.run_smart_network("discover"))
        self.assertFalse(result["home_assistant_paired"])
        self.assertFalse(result["control_available"])

    def test_smart_device_writes_always_force_interactive_approval_even_unattended(self):
        from edith.platform.permissions import requires_local_confirmation
        self.assertTrue(requires_local_confirmation("smart_network", {"action": "control"}))
        self.assertTrue(requires_local_confirmation("smart_network", {"action": "mqtt_publish"}))
        self.assertFalse(requires_local_confirmation("smart_network", {"action": "mqtt_read"}))
        self.assertFalse(requires_local_confirmation("smart_network", {"action": "discover"}))

    def test_mqtt_read_is_read_only_tier_zero_and_publish_requires_confirmation(self):
        from edith.platform.permissions import tool_tier
        self.assertEqual(tool_tier("smart_network", {"action": "mqtt_status"}), 0)
        self.assertEqual(tool_tier("smart_network", {"action": "mqtt_read"}), 0)
        self.assertEqual(tool_tier("smart_network", {"action": "mqtt_publish"}), 2)
        from core.action_guard import confirmation_requirement
        prompt = confirmation_requirement(
            "smart_network", {"action": "mqtt_publish", "topic": "home/light", "payload": "ON"}
        )
        self.assertIn("home/light", prompt)
        self.assertIn("ON", prompt)

    def test_temperature_and_entity_domain_are_validated(self):
        state = {"entity_id": "climate.living_room", "state": "heat", "attributes": {}}
        with patch.object(smart_network, "_ha_request", return_value=state):
            with self.assertRaises(ValueError):
                smart_network.run_smart_network(
                    "control", "climate.living_room", "light.turn_on", {}
                )
            with self.assertRaises(ValueError):
                smart_network.run_smart_network(
                    "control", "climate.living_room", "climate.set_temperature", {"temperature": 50}
                )


if __name__ == "__main__":
    unittest.main()
