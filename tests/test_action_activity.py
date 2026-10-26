import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from core.action_activity import activity_outcome, describe_tool_activity


class ActionActivityTests(unittest.TestCase):
    def test_generic_desktop_app_is_visible_in_activity(self):
        label = describe_tool_activity("open_app", {"app_name": "Docker Desktop"})
        self.assertIn("Docker Desktop", label)
        self.assertIn("desktop app", label.lower())

    def test_typing_content_is_not_logged(self):
        secret = "this is private user text"
        label = describe_tool_activity("computer_control", {"action": "type", "text": secret})
        self.assertNotIn(secret, label)
        self.assertIn("content hidden", label)

    def test_message_body_is_not_logged(self):
        secret = "please send my password 123"
        label = describe_tool_activity(
            "send_message",
            {"platform": "WhatsApp", "receiver": "Alex", "message_text": secret},
        )
        self.assertNotIn(secret, label)
        self.assertIn("WhatsApp", label)
        self.assertIn("Alex", label)

    def test_browser_url_does_not_include_query_or_fragment(self):
        label = describe_tool_activity(
            "browser_control",
            {"action": "go_to", "url": "https://example.com/path?token=private#section"},
        )
        self.assertIn("https://example.com/path", label)
        self.assertNotIn("private", label)
        self.assertNotIn("section", label)

    def test_app_name_filter_matches_multiple_words_and_deduplicates(self):
        from actions.open_app import filter_app_names

        result = filter_app_names(
            ["Docker Desktop", "Docker Desktop", "MongoDB Compass", "Postman", "Android Studio"],
            query="mongo compass",
            limit=10,
        )
        self.assertEqual(result, ["MongoDB Compass"])

    def test_app_name_filter_caps_results_and_ignores_empty_names(self):
        from actions.open_app import filter_app_names

        result = filter_app_names(["", "Postman", "Docker", "Android Studio"], limit=2)
        self.assertEqual(result, ["Android Studio", "Docker"])

    def test_app_search_checks_full_inventory_before_display_limit(self):
        from actions.open_app import filter_app_names

        names = [f"Utility {index:03d}" for index in range(150)]
        names.append("Postman")
        result = filter_app_names(names, query="postman", limit=3000)
        self.assertEqual(result, ["Postman"])

    def test_app_discovery_activity_does_not_claim_launch(self):
        label = describe_tool_activity("open_app", {"action": "list"})
        self.assertIn("Discover installed desktop app launchers", label)

    def test_foreground_verification_rejects_short_unrelated_titles(self):
        from actions import open_app as app_module

        with patch.object(app_module, "_SYSTEM", "Windows"):
            self.assertFalse(
                app_module._foreground_matches("WhatsApp", "WhatsApp", "W")
            )

    def test_open_app_only_claims_launch_when_foreground_matches(self):
        from actions import open_app as app_module

        with (
            patch.object(app_module, "_SYSTEM", "Windows"),
            patch.object(app_module, "_OS_LAUNCHERS", {"Windows": lambda _name: True}),
            patch.object(app_module, "_active_window_description", return_value="Docker Desktop"),
            patch.object(app_module.time, "sleep"),
        ):
            result = app_module.open_app({"app_name": "Docker Desktop"})
        self.assertIn("foreground window verified", result)

    def test_open_app_does_not_claim_success_for_an_unrelated_foreground(self):
        from actions import open_app as app_module

        with (
            patch.object(app_module, "_SYSTEM", "Windows"),
            patch.object(app_module, "_OS_LAUNCHERS", {"Windows": lambda _name: True}),
            patch.object(app_module, "_active_window_description", return_value="EDITH Personal Assistant"),
            patch.object(app_module.time, "sleep"),
        ):
            result = app_module.open_app({"app_name": "Docker Desktop"})
        self.assertIn("not confirmed as the foreground window", result)
        self.assertNotIn("Opened Docker Desktop;", result)

    def test_permanent_delete_removes_one_named_file_inside_home(self):
        import os
        import tempfile
        from pathlib import Path
        from actions.file_controller import delete_file_permanently

        with tempfile.TemporaryDirectory(dir=str(Path.home())) as tmp:
            target = Path(tmp) / "target.txt"
            target.write_text("remove me", encoding="utf-8")
            result = delete_file_permanently(tmp, name="target.txt")
            self.assertIn("Permanently deleted", result)
            self.assertFalse(target.exists())

    def test_permanent_delete_can_remove_an_explicit_user_folder_after_confirmation(self):
        from pathlib import Path
        from actions.file_controller import delete_file_permanently

        with tempfile.TemporaryDirectory(dir=str(Path.home())) as tmp:
            child = Path(tmp) / "child.txt"
            child.write_text("remove me", encoding="utf-8")
            result = delete_file_permanently(tmp)
            self.assertIn("Permanently deleted", result)
            self.assertFalse(Path(tmp).exists())
            self.assertFalse(child.exists())

    def test_permanent_delete_refuses_standard_home_roots(self):
        from actions.file_controller import delete_file_permanently

        result = delete_file_permanently(str(Path.home()), name="")
        self.assertTrue("Protected directory" in result or "Access denied" in result)

    def test_app_discovery_does_not_launch_an_application(self):
        from actions import open_app as app_module

        with (
            patch.object(app_module, "list_installed_apps", return_value="Installed desktop apps: Postman"),
            patch.object(app_module, "_OS_LAUNCHERS") as launchers,
        ):
            result = app_module.open_app({"action": "list"})
        self.assertIn("Postman", result)
        launchers.__getitem__.assert_not_called()

    def test_results_are_classified_without_echoing_contents(self):
        self.assertEqual(activity_outcome("Opened WhatsApp."), "ok")
        self.assertEqual(activity_outcome("Could not launch app."), "error")
        self.assertEqual(activity_outcome("No results were found."), "warning")
        self.assertEqual(
            activity_outcome("Launch request submitted for Docker Desktop, but I could not verify that it opened."),
            "warning",
        )


if __name__ == "__main__":
    unittest.main()
