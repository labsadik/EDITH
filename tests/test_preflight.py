"""Preflight must work when invoked directly from the scripts directory."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PreflightPathTests(unittest.TestCase):
    def test_repository_root_is_added_before_any_application_import(self):
        source = (ROOT / "scripts" / "edith_preflight.py").read_text(encoding="utf-8")
        root_insert = source.index('sys.path.insert(0, str(ROOT))')
        first_core_import = source.index("from core.provider_registry")
        self.assertLess(root_insert, first_core_import)

    def test_preflight_uses_the_same_packaged_config_path_as_runtime(self):
        source = (ROOT / "scripts" / "edith_preflight.py").read_text(encoding="utf-8")
        self.assertIn("from core.app_paths import config_path", source)
        self.assertIn("CONFIG = config_path()", source)


if __name__ == "__main__":
    unittest.main()
