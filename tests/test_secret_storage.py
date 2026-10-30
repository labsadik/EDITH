"""OS keychain migration and legacy fallback tests without a real credential store."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import secrets


class _FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, name):
        return self.values.get((service, name))

    def set_password(self, service, name, value):
        self.values[(service, name)] = value


class SecretStorageTests(unittest.TestCase):
    def test_legacy_key_migrates_only_after_keyring_accepts_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({"gemini_api_key": "legacy-secret-123", "llm_model": "local"}))
            fake = _FakeKeyring()
            with patch("core.secrets._keyring_backend", return_value=fake):
                status = secrets.gemini_key_status(path)
            self.assertEqual(status.storage, "migrated")
            self.assertEqual(status.value, "legacy-secret-123")
            self.assertEqual(fake.values[(secrets.SERVICE_NAME, secrets.GEMINI_SECRET)], "legacy-secret-123")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("gemini_api_key", data)
            self.assertEqual(data["llm_model"], "local")
            self.assertEqual(data["secret_storage"], "os_keyring")

    def test_save_scrubs_plaintext_only_after_secure_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text(json.dumps({"gemini_api_key": "old", "voice_mode": "female"}))
            fake = _FakeKeyring()
            with patch("core.secrets._keyring_backend", return_value=fake):
                status = secrets.save_gemini_api_key("fresh-secret-456", path)
            self.assertEqual(status.storage, "keyring")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("gemini_api_key", data)
            self.assertEqual(data["voice_mode"], "female")

    def test_no_keychain_keeps_legacy_value_and_never_claims_secure_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            with patch("core.secrets._keyring_backend", return_value=None):
                status = secrets.save_gemini_api_key("fallback-secret-789", path)
                reread = secrets.gemini_key_status(path)
            self.assertEqual(status.storage, "legacy")
            self.assertEqual(reread.storage, "legacy")
            self.assertIn("gemini_api_key", json.loads(path.read_text(encoding="utf-8")))

    def test_runtime_key_readers_use_the_shared_secret_module(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "main.py", "dashboard/server.py", "actions/code_helper.py",
            "actions/file_processor.py", "actions/screen_processor.py",
            "actions/web_search.py", "actions/youtube_video.py", "actions/flight_finder.py",
            "actions/upload_video.py", "actions/desktop.py", "actions/computer_control.py",
            "actions/computer_settings.py", "ui.py",
        ):
            with self.subTest(path=relative):
                self.assertIn("get_gemini_api_key", (root / relative).read_text(encoding="utf-8"))
        # Coding/planning now uses the Powerful Brain profile, whose provider
        # credentials are resolved by the shared provider_registry secret helper.
        dev_agent = (root / "actions/dev_agent.py").read_text(encoding="utf-8")
        self.assertIn('profile="powerful"', dev_agent)
        self.assertIn("call_llm_text", dev_agent)


if __name__ == "__main__":
    unittest.main()
