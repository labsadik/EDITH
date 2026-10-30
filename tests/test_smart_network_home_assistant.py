"""Authenticated Home Assistant write-control guardrail tests."""
import json
from unittest.mock import patch

import pytest

from agents import smart_network
from core.action_guard import confirmation_requirement
from edith.platform.permissions import tool_tier


def test_paired_light_service_control_calls_authenticated_adapter():
    state = {"entity_id": "light.living_room", "state": "off", "attributes": {}}
    with patch.object(smart_network, "_ha_request", side_effect=[state, [{"entity_id": "light.living_room"}]]) as request:
        result = json.loads(smart_network.run_smart_network(
            "control", "light.living_room", "light.turn_on", {"brightness_pct": 60}
        ))
    assert result["ok"] is True
    assert result["service"] == "light.turn_on"
    assert request.call_args.args == ("POST", "services/light/turn_on")


def test_smart_home_write_is_tier_two_and_requires_confirmation():
    args = {"action": "control", "entity_id": "switch.fan", "service": "switch.turn_off"}
    assert tool_tier("smart_network", args) == 2
    prompt = confirmation_requirement("smart_network", args)
    assert prompt and "switch.fan" in prompt and "switch.turn_off" in prompt


def test_unapproved_service_is_rejected_before_write():
    state = {"entity_id": "light.living_room", "state": "off", "attributes": {}}
    with patch.object(smart_network, "_ha_request", return_value=state) as request:
        with pytest.raises(ValueError):
            smart_network.run_smart_network("control", "light.living_room", "shell.execute", {})
    request.assert_not_called()


def test_discovery_works_without_home_assistant_pairing():
    with (
        patch.object(smart_network, "_neighbors", return_value=([], "ip")),
        patch.object(smart_network, "_interfaces", return_value={}),
        patch.object(smart_network, "_ha_credentials", return_value=None),
    ):
        result = json.loads(smart_network.run_smart_network("discover"))
    assert result["home_assistant_paired"] is False
    assert result["control_available"] is False


def test_temperature_and_entity_domain_are_validated():
    state = {"entity_id": "climate.living_room", "state": "heat", "attributes": {}}
    with patch.object(smart_network, "_ha_request", return_value=state):
        with pytest.raises(ValueError):
            smart_network.run_smart_network(
                "control", "climate.living_room", "light.turn_on", {}
            )
        with pytest.raises(ValueError):
            smart_network.run_smart_network(
                "control", "climate.living_room", "climate.set_temperature", {"temperature": 50}
            )
