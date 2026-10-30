"""URL normalization tests for the embedded browser without Qt WebEngine runtime."""
import unittest

from core.embedded_browser import normalize_web_url


class EmbeddedBrowserURLTests(unittest.TestCase):
    def test_accepts_https_and_bare_domains(self):
        self.assertEqual(normalize_web_url("https://example.com").scheme(), "https")
        self.assertEqual(normalize_web_url("example.com").host(), "example.com")

    def test_turns_search_terms_into_google_search(self):
        url = normalize_web_url("EDITH assistant documentation")
        self.assertEqual(url.host(), "www.google.com")
        self.assertIn("EDITH%20assistant%20documentation", bytes(url.toEncoded()).decode("ascii"))

    def test_rejects_non_web_schemes(self):
        for target in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,hello"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    normalize_web_url(target)


if __name__ == "__main__":
    unittest.main()
