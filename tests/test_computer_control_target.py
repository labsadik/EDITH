import unittest
from unittest.mock import patch

from actions import computer_control as control_module


class ConfirmedForegroundTargetTests(unittest.TestCase):
    def test_confirmed_action_restores_and_verifies_target_before_typing(self):
        with (
            patch.object(control_module, "_focus_window", return_value="Focused window: Terminal"),
            patch("actions.open_app._active_window_description", return_value="Terminal — project shell"),
            patch.object(control_module, "_type", return_value="Typed") as type_text,
        ):
            result = control_module.computer_control({
                "action": "type",
                "text": "git status",
                "_confirmed_window_target": "Terminal",
            })
        self.assertEqual(result, "Typed")
        type_text.assert_called_once_with("git status")

    def test_confirmed_action_stops_if_focus_cannot_be_verified(self):
        with (
            patch.object(control_module, "_focus_window", return_value="Could not find/focus window"),
            patch.object(control_module, "_type", return_value="Typed") as type_text,
        ):
            result = control_module.computer_control({
                "action": "type",
                "text": "dangerous input",
                "_confirmed_window_target": "Terminal",
            })
        self.assertIn("no computer action executed", result)
        type_text.assert_not_called()

    def test_confirmed_action_stops_if_an_unrelated_window_is_foreground(self):
        with (
            patch.object(control_module, "_focus_window", return_value="Focused window: Terminal"),
            patch("actions.open_app._active_window_description", return_value="EDITH Personal Assistant"),
            patch.object(control_module, "_type", return_value="Typed") as type_text,
        ):
            result = control_module.computer_control({
                "action": "type",
                "text": "dangerous input",
                "_confirmed_window_target": "Terminal",
            })
        self.assertIn("could not be verified", result)
        type_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
