"""Theme preference and OS-observation contracts without a physical desktop."""
from __future__ import annotations

import unittest

from core.theme_service import SystemThemeMonitor, normalise_theme


class ThemeServiceTests(unittest.TestCase):
    def test_normalises_only_supported_palette_names(self):
        self.assertEqual(normalise_theme("LIGHT"), "light")
        self.assertEqual(normalise_theme("dark"), "dark")
        self.assertEqual(normalise_theme("system"), "dark")
        self.assertEqual(normalise_theme(None, "light"), "light")

    def test_monitor_accepts_structured_platform_probe(self):
        monitor = SystemThemeMonitor(lambda _theme: None, read_theme=lambda: {
            "theme": "light", "source": "mock", "known": True,
        })
        self.assertEqual(monitor._sample(), "light")

    def test_monitor_falls_back_without_propagating_probe_errors(self):
        def unavailable():
            raise OSError("platform setting unavailable")
        monitor = SystemThemeMonitor(lambda _theme: None, read_theme=unavailable)
        self.assertEqual(monitor._sample(), "dark")


class NativeThemeContractTests(unittest.TestCase):
    def test_ui_uses_threaded_monitor_and_persisted_preferences(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "ui.py").read_text(encoding="utf-8")
        self.assertIn('"system", "dark", "light"', source)
        self.assertIn('data["ui_theme"] = self._theme_preference', source)
        self.assertIn('SystemThemeMonitor(self.theme_changed_signal.emit, interval=2.0)', source)
        self.assertIn('theme_changed_signal = pyqtSignal(str)', source)
        self.assertIn('self._theme_monitor.stop()', source)

