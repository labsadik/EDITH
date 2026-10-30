"""Offline DevSecOps checks are local, bounded and non-mutating."""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest

from agents.devsecops import scan_project, format_report


class DevSecOpsTests(unittest.TestCase):
    def test_finds_common_high_risk_patterns_without_echoing_secret_value(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "app.py").write_text(
                "API_KEY = 'sk_test_12345678901234567890'\n"
                "result = eval(user_input)\n"
                "subprocess.run(command, shell=True)\n",
                encoding="utf-8",
            )
            report = scan_project(root)
        rules = {item["rule"] for item in report["findings"]}
        self.assertIn("hardcoded-credential", rules)
        self.assertIn("dynamic-code", rules)
        self.assertIn("unsafe-shell", rules)
        formatted = format_report(report)
        self.assertNotIn("sk_test_12345678901234567890", formatted)
        self.assertIn("not a penetration test", formatted)

    def test_ignores_virtualenv_and_symlinked_project_files(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            root, external = Path(folder), Path(outside)
            (root / ".venv").mkdir()
            (root / ".venv" / "unsafe.py").write_text("eval(x)", encoding="utf-8")
            outside_file = external / "unsafe.py"
            outside_file.write_text("exec(x)", encoding="utf-8")
            try:
                (root / "linked.py").symlink_to(outside_file)
            except OSError:
                pass
            report = scan_project(root)
        self.assertEqual(report["files_inspected"], 0)
        self.assertEqual(report["findings"], [])


if __name__ == "__main__":
    unittest.main()
