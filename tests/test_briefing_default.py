"""Startup briefing default policy tests."""
import unittest
from unittest.mock import patch

from memory import config_manager


class BriefingDefaultTests(unittest.TestCase):
    def test_morning_briefing_defaults_to_disabled(self):
        with patch.object(config_manager, "load_api_keys", return_value={}):
            self.assertFalse(config_manager.get_brief_enabled())

    def test_explicit_user_briefing_preference_is_preserved(self):
        with patch.object(config_manager, "load_api_keys", return_value={"morning_brief_enabled": True}):
            self.assertTrue(config_manager.get_brief_enabled())
        with patch.object(config_manager, "load_api_keys", return_value={"morning_brief_enabled": False}):
            self.assertFalse(config_manager.get_brief_enabled())


if __name__ == "__main__":
    unittest.main()
