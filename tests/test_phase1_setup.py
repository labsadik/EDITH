"""Phase 1: startup, EDITH naming and lossless upgrade contracts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.branding import prepare_agent_profiles_dir, prepare_projects_dir, prepare_uploads_dir
from core.icons import icon_names, svg_markup
from core.app_icon import build_edith_icon
from core.startup_check import (
    bootstrap_missing_dependencies, format_install_help, missing_startup_dependencies,
)
from memory import config_manager


ROOT = Path(__file__).resolve().parents[1]


class _MemoryKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, name):
        return self.values.get((service, name))

    def set_password(self, service, name, value):
        self.values[(service, name)] = value


class BrandingAndStartupTests(unittest.TestCase):
    def setUp(self):
        # These tests exercise the config/keychain contract without changing
        # the developer's real OS credential store or leaking state to the
        # next test's temporary config file.
        backend = patch("core.secrets._keyring_backend", return_value=_MemoryKeyring())
        backend.start()
        self.addCleanup(backend.stop)

    def test_old_upload_directory_migrates_with_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            dl = home / "Downloads"
            old = dl / "JARVIS Uploads"
            old.mkdir(parents=True)
            (old / "notes.txt").write_text("keep me", encoding="utf-8")
            target = prepare_uploads_dir(home=home, base_dir=Path(tmp))
            self.assertEqual(target, dl / "EDITH Uploads")
            self.assertEqual((target / "notes.txt").read_text(), "keep me")
            self.assertFalse(old.exists())

    def test_collisions_do_not_overwrite_old_or_new_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            dl = home / "Downloads"
            old, new = dl / "JARVIS Uploads", dl / "EDITH Uploads"
            old.mkdir(parents=True)
            new.mkdir()
            (old / "report.pdf").write_text("old", encoding="utf-8")
            (new / "report.pdf").write_text("new", encoding="utf-8")
            path = prepare_uploads_dir(home=home, base_dir=Path(tmp))
            self.assertEqual(path, new)
            self.assertEqual((new / "report.pdf").read_text(), "new")
            self.assertEqual((new / "report_migrated_1.pdf").read_text(), "old")
            self.assertFalse(old.exists())

    def test_symlink_is_not_migrated_or_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            dl = home / "Downloads"
            old = dl / "JARVIS Uploads"
            old.mkdir(parents=True)
            outside = Path(tmp) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                (old / "linked.txt").symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            path = prepare_uploads_dir(home=home, base_dir=Path(tmp))
            self.assertEqual(outside.read_text(), "outside")
            self.assertFalse((path / "linked.txt").exists())

    def test_neutral_upload_fallback_when_user_folders_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "repo"
            path = prepare_uploads_dir(home=Path(tmp) / "empty", base_dir=base)
            self.assertEqual(path, base / "uploads")
            self.assertTrue(path.is_dir())

    def test_browser_profile_and_sign_ins_survive_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source = home / ".jarvis_profiles" / "chrome"
            source.mkdir(parents=True)
            (source / "Cookies").write_bytes(b"retained browser data")
            target = prepare_agent_profiles_dir(home)
            self.assertEqual(target, home / ".edith_profiles")
            self.assertEqual((target / "chrome" / "Cookies").read_bytes(),
                             b"retained browser data")

    def test_previous_generated_projects_survive_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source = home / "Desktop" / "JarvisProjects" / "sample"
            source.mkdir(parents=True)
            (source / "main.py").write_text("print('keep')", encoding="utf-8")
            target = prepare_projects_dir(home)
            self.assertEqual(target, home / "Desktop" / "EDITH Projects")
            self.assertEqual(
                (target / "sample" / "main.py").read_text(encoding="utf-8"),
                "print('keep')",
            )

    def test_missing_dependencies_provide_exact_install_command(self):
        missing = missing_startup_dependencies(
            lambda name: None if name == "sounddevice" else object()
        )
        self.assertEqual(missing, [("sounddevice", "sounddevice")])
        msg = format_install_help(missing)
        self.assertIn("python -m pip install -r requirements.txt", msg)
        self.assertIn("python main.py", msg)
        self.assertIn("local-LLM settings are not modified", msg)

    def test_missing_parent_module_is_handled(self):
        def checker(name):
            if name == "google.genai":
                raise ModuleNotFoundError("No module named 'google'")
            return object()
        self.assertEqual(
            missing_startup_dependencies(checker),
            [("google.genai", "google-genai>=2.8.0")],
        )

    def test_missing_runtime_tools_are_bootstrapped_from_static_installer(self):
        present = {name: object() for name, _ in __import__("core.startup_check", fromlist=["STARTUP_IMPORTS"]).STARTUP_IMPORTS}
        calls = []
        def checker(name):
            return present.get(name)
        def install(_config, _log):
            calls.append(True)
            present["sounddevice"] = object()
        present.pop("sounddevice")
        self.assertEqual(bootstrap_missing_dependencies(checker, install), [])
        self.assertEqual(calls, [True])

    def test_edith_ico_has_real_windows_icon_sizes(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed in this test environment")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "edith.ico"
            self.assertTrue(build_edith_icon(dest))
            with Image.open(dest) as icon:
                self.assertEqual(icon.format, "ICO")
                self.assertIn((16, 16), icon.ico.sizes())
                self.assertIn((32, 32), icon.ico.sizes())
                self.assertIn((256, 256), icon.ico.sizes())

    def test_fixed_icon_is_part_of_the_local_svg_set(self):
        self.assertIn("edith-app", icon_names())
        svg = svg_markup("edith-app")
        self.assertIn("<svg", svg)
        self.assertIn("M16.5 6.5", svg)

    def test_launcher_and_autostart_new_names_are_edith(self):
        ui = (ROOT / "ui.py").read_text(encoding="utf-8")
        for snippet in (
            'desktop / "EDITH.lnk"', 'desktop / "EDITH.app"',
            'desktop / "edith.desktop"', 'desk_dir / "edith.desktop"',
            'winreg.SetValueEx(\n                            reg, "EDITH"',
            'config" / "edith.ico"', 'svg_icon("edith-app"',
        ):
            self.assertIn(snippet, ui)
        for forbidden in (
            'desktop / "AI Assistant.lnk"',
            'desktop / "AI Assistant.app"',
            'desk = desktop / "ai-assistant.desktop"',
            'winreg.SetValueEx(reg, "JARVIS_AI"',
        ):
            self.assertNotIn(forbidden, ui)

    def test_early_preflight_and_lazy_upload_creation(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        dash = (ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertLess(main.index("check_startup_dependencies()"), main.index("import sounddevice as sd"))
        self.assertIn("self._uploads_dir                 = _make_uploads_dir()", dash)
        self.assertNotIn("UPLOADS_DIR = _make_uploads_dir()", dash)
        self.assertIn("def _certificate_paths()", dash)

    def test_first_run_setup_preserves_existing_cloud_and_local_credentials(self):
        old_path = config_manager.CONFIG_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config_manager.CONFIG_FILE = Path(tmp) / "api_keys.json"
                saved = {
                    "gemini_api_key": "previous-key",
                    "llm_provider": "openai",
                    "llm_url": "http://127.0.0.1:1234",
                    "llm_model": "custom-local-model",
                    "voice_mode": "male",
                    "plugins_enabled": {"notes": False},
                    "user_name": "Person",
                }
                import json
                config_manager.CONFIG_FILE.write_text(json.dumps(saved), encoding="utf-8")
                config_manager.save_initial_setup("new-gemini-key", "Windows")
                after = config_manager.load_api_keys()
                for key in ("llm_provider", "llm_url", "llm_model",
                            "voice_mode", "plugins_enabled", "user_name"):
                    self.assertEqual(after[key], saved[key], key)
                self.assertEqual(after["gemini_api_key"], "new-gemini-key")
                self.assertEqual(after["os_system"], "Windows")
                self.assertEqual(after["assistant_name"], "EDITH")
        finally:
            config_manager.CONFIG_FILE = old_path

    def test_first_run_setup_refuses_to_overwrite_corrupt_config(self):
        old_path = config_manager.CONFIG_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config_manager.CONFIG_FILE = Path(tmp) / "api_keys.json"
                bad_data = '{"gemini_api_key": "dont-replace"'
                config_manager.CONFIG_FILE.write_text(bad_data, encoding="utf-8")
                with self.assertRaises(ValueError):
                    config_manager.save_initial_setup("new-key", "Windows")
                self.assertEqual(
                    config_manager.CONFIG_FILE.read_text(encoding="utf-8"), bad_data,
                )
        finally:
            config_manager.CONFIG_FILE = old_path

    def test_initial_setup_creates_new_config_without_old_brand(self):
        old_path = config_manager.CONFIG_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config_manager.CONFIG_FILE = Path(tmp) / "config" / "api_keys.json"
                config_manager.save_initial_setup("api-key", "Windows")
                self.assertEqual(config_manager.load_api_keys()["assistant_name"], "EDITH")
        finally:
            config_manager.CONFIG_FILE = old_path

    def test_saving_profile_does_not_erase_cloud_or_local_settings(self):
        old_path = config_manager.CONFIG_FILE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config_manager.CONFIG_FILE = Path(tmp) / "api_keys.json"
                config_manager.CONFIG_FILE.write_text(
                    '{"gemini_api_key":"secret","llm_provider":"openai",'
                    '"llm_url":"http://127.0.0.1:1234","llm_model":"local-model"}',
                    encoding="utf-8",
                )
                config_manager.save_assistant_config("anything", "Tester")
                data = config_manager.load_api_keys()
                self.assertEqual(data["assistant_name"], "EDITH")
                self.assertEqual(data["gemini_api_key"], "secret")
                self.assertEqual(data["llm_provider"], "openai")
                self.assertEqual(data["llm_url"], "http://127.0.0.1:1234")
                self.assertEqual(data["llm_model"], "local-model")
        finally:
            config_manager.CONFIG_FILE = old_path


if __name__ == "__main__":
    unittest.main()


