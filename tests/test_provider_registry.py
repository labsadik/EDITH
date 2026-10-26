"""Provider profiles preserve local compatibility and never log API keys."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import llm_client
from core import provider_registry as providers


class _FakeKeyring:
    def __init__(self): self.values = {}
    def get_password(self, service, name): return self.values.get((service, name))
    def set_password(self, service, name, value): self.values[(service, name)] = value


class ProviderRegistryTests(unittest.TestCase):
    def test_existing_local_openai_profile_stays_local_and_keyless(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({"llm_provider": "openai", "llm_url": "http://127.0.0.1:1234", "llm_model": "qwen"}))
            settings = providers.load_provider_settings(path)
            self.assertEqual(settings["provider"], "openai_compatible")
            self.assertEqual(settings["model"], "qwen")

    def test_cloud_provider_saves_key_to_keyring_and_selection_to_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"; fake = _FakeKeyring()
            with patch("core.secrets._keyring_backend", return_value=fake):
                settings = providers.save_provider_settings(path, "anthropic", "https://api.anthropic.com/v1", "claude-test", "provider-secret-123")
            data = json.loads(path.read_text())
            self.assertEqual(settings["provider"], "anthropic")
            self.assertEqual(data["provider_profile"], "anthropic")
            self.assertNotIn("anthropic_api_key", data)
            self.assertEqual(fake.values[("EDITH", "anthropic_api_key")], "provider-secret-123")

    def test_openai_endpoint_does_not_duplicate_v1(self):
        self.assertEqual(llm_client._openai_endpoint("https://api.openai.com/v1", "/models"), "https://api.openai.com/v1/models")
        self.assertEqual(llm_client._openai_endpoint("http://localhost:1234", "/models"), "http://localhost:1234/v1/models")

    def test_anthropic_response_is_normalized_to_canonical_text(self):
        response = Mock(); response.json.return_value = {"content": [{"type": "text", "text": " OK "}]}
        with (patch.object(llm_client, "get_llm_provider", return_value="anthropic"),
              patch.object(llm_client, "get_llm_settings", return_value=("https://api.anthropic.com/v1", "claude-test")),
              patch.object(llm_client, "_cloud_headers", return_value={"x-api-key": "hidden"}),
              patch.object(llm_client.requests, "post", return_value=response) as post):
            result = llm_client.call_llm([{"role": "user", "content": "hello"}])
        self.assertEqual(result, {"content": "OK", "tool_calls": []})
        self.assertTrue(post.call_args.args[0].endswith("/messages"))

    def test_probe_reports_structured_failure_without_key_text(self):
        with patch.object(providers.requests, "post", side_effect=RuntimeError("provider-secret-123 rejected")):
            result = providers.probe_provider("openai", "https://api.openai.com/v1", "gpt-test", "provider-secret-123")
        self.assertFalse(result["ok"])
        self.assertIn("RuntimeError", result["error"])
        # The UI caller passes this to a label, so it must never echo the key.
        self.assertNotIn("provider-secret-123", result["error"])


if __name__ == "__main__":
    unittest.main()

