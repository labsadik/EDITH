"""Packaged EDITH config must be writable and isolated per Windows user."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import app_paths


class AppPathTests(unittest.TestCase):
    def test_source_checkout_keeps_repository_config_location(self):
        path = app_paths.config_path()
        self.assertEqual(path, Path(__file__).resolve().parents[1] / "config" / "api_keys.json")

    def test_packaged_install_migrates_existing_config_to_per_user_appdata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install = root / "Program Files" / "EDITH"
            legacy = install / "config" / "api_keys.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"llm_provider":"openai","openai_api_key":"private"}', encoding="utf-8")
            appdata = root / "User" / "AppData" / "Roaming"
            executable = install / "EDITH.exe"
            with (
                patch.object(app_paths, "is_frozen", return_value=True),
                patch.object(app_paths.sys, "executable", str(executable)),
                patch.object(app_paths.platform, "system", return_value="Windows"),
                patch.dict(os.environ, {"APPDATA": str(appdata)}),
            ):
                target = app_paths.config_path()
            self.assertEqual(target, appdata / "EDITH" / "config" / "api_keys.json")
            self.assertEqual(target.read_text(encoding="utf-8"), legacy.read_text(encoding="utf-8"))
            self.assertTrue(legacy.is_file(), "Migration must not delete the legacy installation copy")


    def test_packaged_config_templates_are_copied_into_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root / "bundle"
            template = bundle / "config" / "mcp_servers.json"
            template.parent.mkdir(parents=True)
            template.write_text('{"servers":[]}', encoding="utf-8")
            appdata = root / "AppData"
            with (
                patch.object(app_paths, "is_frozen", return_value=True),
                patch.object(app_paths, "resource_dir", return_value=bundle),
                patch.object(app_paths, "install_dir", return_value=root / "Program Files" / "EDITH"),
                patch.object(app_paths.platform, "system", return_value="Windows"),
                patch.dict(os.environ, {"APPDATA": str(appdata)}),
            ):
                target = app_paths.writable_config_path("mcp_servers.json")
            self.assertEqual(target.read_text(encoding="utf-8"), '{"servers":[]}')
            self.assertEqual(target, appdata / "EDITH" / "config" / "mcp_servers.json")


    def test_packaged_memory_and_rag_databases_use_user_writable_storage(self):
        import importlib
        from core import app_paths
        import memory.memory_manager as memory_manager
        import memory.rag_store as rag_store

        with tempfile.TemporaryDirectory() as folder:
            user_data = Path(folder) / "EDITH"
            with (
                patch.object(app_paths, "is_frozen", return_value=True),
                patch.object(app_paths, "app_data_dir", return_value=user_data),
            ):
                importlib.reload(memory_manager)
                importlib.reload(rag_store)
                self.assertEqual(
                    memory_manager.MEMORY_PATH,
                    user_data / "memory" / "long_term.json",
                )
                self.assertEqual(
                    rag_store.VECTOR_DB_PATH,
                    user_data / "memory" / "vector_db",
                )
            # Restore module globals for the remaining source-checkout tests.
            importlib.reload(memory_manager)
            importlib.reload(rag_store)

    def test_existing_per_user_config_is_never_overwritten_by_legacy_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install = root / "EDITH"
            legacy = install / "config" / "api_keys.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"source":"old"}', encoding="utf-8")
            appdata = root / "AppData"
            target = appdata / "EDITH" / "config" / "api_keys.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"source":"new"}', encoding="utf-8")
            with (
                patch.object(app_paths, "is_frozen", return_value=True),
                patch.object(app_paths.sys, "executable", str(install / "EDITH.exe")),
                patch.object(app_paths.platform, "system", return_value="Windows"),
                patch.dict(os.environ, {"APPDATA": str(appdata)}),
            ):
                self.assertEqual(app_paths.config_path(), target)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"source":"new"}')


if __name__ == "__main__":
    unittest.main()
