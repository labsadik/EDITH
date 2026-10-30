"""Powerful Brain configuration is independent from Gemini Live voice transport."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import llm_client
from core.provider_registry import load_provider_settings, save_provider_settings


class PowerfulBrainProfileTests(unittest.TestCase):
    def test_local_ollama_profile_is_saved_without_api_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            result = save_provider_settings(
                path, "ollama", "http://127.0.0.1:11434", "qwen3:8b", profile="powerful"
            )
            self.assertEqual(result["profile"], "powerful")
            self.assertEqual(
                load_provider_settings(path, "powerful"),
                {"provider": "ollama", "url": "http://127.0.0.1:11434", "model": "qwen3:8b"},
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["powerful_provider_profile"], "ollama")
            self.assertNotIn("powerful_openai_api_key", data)

    def test_cloud_api_profile_is_saved_separately_from_voice_and_main(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({
                "llm_provider": "ollama",
                "llm_url": "http://127.0.0.1:11434",
                "llm_model": "llama3.2",
                "voice_provider": "gemini_live",
            }), encoding="utf-8")
            with patch("core.provider_registry.save_config_secret") as save_secret:
                save_provider_settings(
                    path, "openai", "https://api.openai.com/v1", "gpt-4.1-mini",
                    "unit-test-api-key", profile="powerful",
                )
            save_secret.assert_called_once()
            self.assertEqual(load_provider_settings(path, "main")["provider"], "ollama")
            self.assertEqual(load_provider_settings(path, "powerful")["provider"], "openai")
            self.assertEqual(load_provider_settings(path, "powerful")["model"], "gpt-4.1-mini")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["voice_provider"], "gemini_live")

    def test_llm_provider_resolves_powerful_profile_not_main_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({
                "llm_provider": "ollama",
                "powerful_llm_provider": "openai",
                "powerful_provider_profile": "openai",
                "powerful_llm_url": "https://api.openai.com/v1",
                "powerful_llm_model": "gpt-4.1-mini",
            }), encoding="utf-8")
            with patch.object(llm_client, "CONFIG_PATH", path):
                self.assertEqual(llm_client.get_llm_provider("powerful"), "openai")
                self.assertEqual(
                    llm_client.get_llm_settings("powerful"),
                    ("https://api.openai.com/v1", "gpt-4.1-mini"),
                )


if __name__ == "__main__":
    unittest.main()
