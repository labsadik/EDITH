"""URL normalization tests for the embedded browser without Qt WebEngine runtime."""
import json
import unittest

from core.embedded_browser import build_embedded_browser_script, normalize_web_url


class EmbeddedBrowserURLTests(unittest.TestCase):
    def test_accepts_https_and_bare_domains(self):
        self.assertEqual(normalize_web_url("https://example.com").scheme(), "https")
        self.assertEqual(normalize_web_url("example.com").host(), "example.com")

    def test_turns_search_terms_into_google_search(self):
        url = normalize_web_url("EDITH assistant documentation")
        self.assertEqual(url.host(), "www.google.com")
        self.assertIn("EDITH%20assistant%20documentation", bytes(url.toEncoded()).decode("ascii"))

    def test_browser_click_script_uses_encoded_selector_and_rejects_ambiguity(self):
        script = build_embedded_browser_script("click", {"selector": "button.save"})
        self.assertIn("querySelectorAll", script)
        self.assertIn("Target is ambiguous", script)

    def test_text_payload_is_json_encoded_not_executed_as_javascript(self):
        payload = '"); alert("injected"); //'
        script = build_embedded_browser_script("type", {"selector": "#search", "text": payload})
        self.assertIn(json.dumps(payload), script)
        self.assertIn("dispatchEvent", script)

    def test_form_fill_is_bounded_and_does_not_submit(self):
        script = build_embedded_browser_script(
            "fill_form", {"fields": {"#email": "test@example.com", "#name": "EDITH"}}
        )
        self.assertIn("filled.length", script)
        self.assertNotIn(".submit(", script)
        with self.assertRaises(ValueError):
            build_embedded_browser_script("fill_form", {"fields": {}})

    def test_embedded_actions_reject_unapproved_keys_and_actions(self):
        with self.assertRaises(ValueError):
            build_embedded_browser_script("press", {"key": "Delete"})
        with self.assertRaises(ValueError):
            build_embedded_browser_script("evaluate", {"script": "alert(1)"})

    def test_rejects_non_web_schemes(self):
        for target in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,hello"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    normalize_web_url(target)


if __name__ == "__main__":
    unittest.main()
