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

    def test_groq_and_grok_have_separate_model_endpoints(self):
        response = Mock()
        response.json.return_value = {"data": [{"id": "model-alpha"}, {"id": "model-beta"}]}
        with patch.object(providers.requests, "get", return_value=response) as get:
            groq_models = providers.list_provider_models(
                "groq", "https://api.groq.com/openai/v1", "groq-secret"
            )
            self.assertEqual(groq_models, ["model-alpha", "model-beta"])
            self.assertEqual(get.call_args.args[0], "https://api.groq.com/openai/v1/models")
            get.reset_mock()
            xai_models = providers.list_provider_models(
                "xai", "https://api.x.ai/v1", "xai-secret"
            )
            self.assertEqual(get.call_args.args[0], "https://api.x.ai/v1/models")

    def test_main_and_powerful_brain_profiles_keep_separate_keys_and_models(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            fake = _FakeKeyring()
            with patch("core.secrets._keyring_backend", return_value=fake):
                providers.save_provider_settings(
                    path, "groq", "https://api.groq.com/openai/v1",
                    "groq/model-main", "main-secret", profile="main",
                )
                providers.save_provider_settings(
                    path, "xai", "https://api.x.ai/v1",
                    "grok-model", "power-secret", profile="powerful",
                )
                self.assertEqual(providers.load_provider_settings(path)["provider"], "groq")
                self.assertEqual(providers.load_provider_settings(path, "powerful")["provider"], "xai")
                self.assertEqual(providers.provider_api_key("groq", path), "main-secret")
                self.assertEqual(providers.provider_api_key("xai", path, "powerful"), "power-secret")
            data = json.loads(path.read_text())
            self.assertNotIn("groq_api_key", data)
            self.assertNotIn("powerful_xai_api_key", data)
            self.assertEqual(data["powerful_llm_model"], "grok-model")

    def test_powerful_brain_calls_its_own_provider_and_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            fake = _FakeKeyring()
            response = Mock()
            response.json.return_value = {"choices": [{"message": {"content": "power response"}}]}
            with patch("core.secrets._keyring_backend", return_value=fake):
                providers.save_provider_settings(
                    path, "groq", "https://api.groq.com/openai/v1",
                    "groq/model-power", "powerful-secret", profile="powerful",
                )
                with (patch.object(llm_client, "CONFIG_PATH", path),
                      patch.object(llm_client.requests, "post", return_value=response) as post):
                    result = llm_client.call_llm(
                        [{"role": "user", "content": "test"}], profile="powerful"
                    )
            self.assertEqual(result["content"], "power response")
            self.assertEqual(post.call_args.args[0],
                             "https://api.groq.com/openai/v1/chat/completions")
            self.assertEqual(post.call_args.kwargs["headers"]["Authorization"],
                             "Bearer powerful-secret")

    def test_tavily_live_search_normalizes_results(self):
        response = Mock()
        response.json.return_value = {"results": [{
            "title": "Result", "content": "A current source", "url": "https://example.com",
        }]}
        with patch.object(providers.requests, "post", return_value=response) as post:
            results = providers.run_realtime_search("tavily", "current event", "tavily-secret")
        self.assertEqual(results[0]["title"], "Result")
        self.assertEqual(post.call_args.args[0], "https://api.tavily.com/search")
        self.assertEqual(post.call_args.kwargs["json"]["api_key"], "tavily-secret")


if __name__ == "__main__":
    unittest.main()

