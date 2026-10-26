"""Dependency installer must not claim success after a pip failure."""
import unittest
from unittest.mock import patch

from core import installer


class InstallerTruthfulnessTests(unittest.TestCase):
    def test_existing_packages_do_not_trigger_pip(self):
        logs = []
        with patch.object(installer, "_available", return_value=True), \
             patch.object(installer, "_pip") as pip:
            installer.install_for_config({}, log=logs.append)
            pip.assert_not_called()
        self.assertTrue(any("already installed" in line for line in logs))

    def test_failed_package_install_is_reported_and_raises(self):
        logs = []
        with patch.object(installer, "_available", return_value=False), \
             patch.object(installer, "_pip", return_value=False), \
             patch.object(installer.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(RuntimeError, "EDITH dependencies failed"):
                installer.install_for_config({}, log=logs.append)
        self.assertTrue(any("ERR: Dependencies not ready:" in line for line in logs))
        self.assertFalse(any("All dependencies ready" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
