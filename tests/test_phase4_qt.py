"""Headless Qt smoke test for Phase 4; no API, microphone or model calls."""
import json
import os
import tempfile
import unittest
from pathlib import Path


# Qt must choose its headless platform *before* QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class Phase4QtSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PyQt6.QtWidgets import QApplication
            import ui
        except ImportError as exc:
            # CI must run GUI smoke tests, not silently skip due missing Qt libs.
            if os.environ.get("CI", "").lower() == "true":
                raise RuntimeError(f"Headless Qt runtime unavailable in CI: {exc}") from exc
            raise unittest.SkipTest(f"PyQt6 runtime not installed: {exc}") from exc
        cls.ui = ui
        cls.app = QApplication.instance() or QApplication(["edith-phase4-qt-test"])
        cls.tmp = tempfile.TemporaryDirectory()
        cls.original_api_file = ui.API_FILE
        ui.API_FILE = Path(cls.tmp.name) / "api_keys.json"
        ui.API_FILE.write_text(json.dumps({
            "gemini_api_key": "test-only-not-valid",
            "os_system": "Windows",
        }), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.ui.API_FILE = cls.original_api_file
        cls.tmp.cleanup()

    def setUp(self):
        self.window = self.ui.MainWindow("nonexistent-test-face.png")
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        # Exercise the same close path used by the running app. Hiding a Qt
        # window only pauses QMediaPlayer; it does not release the FFmpeg
        # decoder/sink. Repeated headless UI tests otherwise leave decoder
        # workers alive and can segfault when QApplication tears down.
        self.window.close()
        self.window.hud.shutdown()
        self.app.processEvents()
        self.window.deleteLater()
        self.app.sendPostedEvents()
        self.app.processEvents()

    def test_existing_hud_preserved_and_task_rows_expand(self):
        window = self.window
        self.assertEqual(window.windowTitle(), "EDITH • PERSONAL ASSISTANT")
        self.assertIsNotNone(window.hud)
        self.assertFalse(window._task_details_btn.isEnabled())

        window.task_detail_signal.emit({
            "total": 2,
            "visible": [
                {"label": "Read project structure", "status": "running"},
                {"label": "Find documentation", "status": "queued"},
            ],
        })
        window.task_status_signal.emit(1, 1, 0)
        self.app.processEvents()
        self.assertTrue(window._task_details_btn.isEnabled())
        window._task_details_btn.setChecked(True)
        self.app.processEvents()
        self.assertTrue(window._task_details_panel.isVisible())
        self.assertIn("Read project", window._task_detail_rows[0][1].toolTip())
        self.assertEqual(window._task_detail_rows[1][2].text(), "QUEUED")
        self.assertFalse(window._task_detail_rows[2][0].isVisible())
        self.assertTrue(window._cancel_queued_btn.isEnabled())

    def test_compact_resize_and_command_focus(self):
        window = self.window
        window.resize(840, 560)
        self.app.processEvents()
        self.assertLessEqual(window._right_panel.width(), 300)
        self.assertLessEqual(window._left_panel.width(), 150)
        window._input.setText("retain typed text")
        window._focus_command_input()
        self.assertTrue(window._input.hasFocus())
        self.assertEqual(window._input.selectedText(), "retain typed text")

    def test_unsent_commands_are_preserved_without_overwriting_new_drafts(self):
        window = self.window
        window.on_text_command = lambda message: False
        window._input.setText("retry this command")
        window._send()
        self.assertEqual(window._input.text(), "retry this command")

        window.on_text_command = lambda message: True
        window._send()
        self.assertEqual(window._input.text(), "")
        window.text_send_failed_signal.emit("retry this command")
        self.app.processEvents()
        self.assertEqual(window._input.text(), "retry this command")

        window._input.setText("a newer draft")
        window.text_send_failed_signal.emit("older failed command")
        self.app.processEvents()
        self.assertEqual(window._input.text(), "a newer draft")

    def test_hud_shutdown_detaches_multimedia_resources_and_is_idempotent(self):
        video = self.window.hud._video
        self.window.hud.shutdown()
        self.assertIsNone(video.player)
        self.assertIsNone(video.sink)
        self.window.hud.shutdown()

    def test_reduced_motion_is_ui_only_and_preserves_text(self):
        window = self.window
        window._log.set_reduced_motion(True)
        window._log.append_log("SYS: EDITH activity test")
        self.app.processEvents()
        # One step writes a full line rather than one character.
        window._log._step()
        self.assertIn("SYS: EDITH activity test", window._log.toPlainText())
        window._log.set_reduced_motion(False)


if __name__ == "__main__":
    unittest.main()

