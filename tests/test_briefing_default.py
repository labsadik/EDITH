"""Startup briefing default policy tests."""
from unittest.mock import patch

from memory import config_manager


def test_morning_briefing_defaults_to_disabled():
    with patch.object(config_manager, "load_api_keys", return_value={}):
        assert config_manager.get_brief_enabled() is False


def test_explicit_user_briefing_preference_is_preserved():
    with patch.object(config_manager, "load_api_keys", return_value={"morning_brief_enabled": True}):
        assert config_manager.get_brief_enabled() is True
    with patch.object(config_manager, "load_api_keys", return_value={"morning_brief_enabled": False}):
        assert config_manager.get_brief_enabled() is False
