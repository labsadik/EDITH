"""URL normalization tests for the embedded browser without starting Qt."""
import pytest

from core.embedded_browser import normalize_web_url


def test_embedded_browser_accepts_https_and_domains():
    assert normalize_web_url("https://example.com").scheme() == "https"
    assert normalize_web_url("example.com").host() == "example.com"


def test_embedded_browser_turns_search_terms_into_google_search():
    url = normalize_web_url("EDITH assistant documentation")
    assert url.host() == "www.google.com"
    assert "EDITH%20assistant%20documentation" in url.toString()


@pytest.mark.parametrize("target", ["javascript:alert(1)", "file:///etc/passwd", "data:text/html,hello"])
def test_embedded_browser_rejects_non_web_schemes(target):
    with pytest.raises(ValueError):
        normalize_web_url(target)
