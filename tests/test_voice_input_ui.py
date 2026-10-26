"""Regression coverage for EDITH's real-input, display-only HUD feedback."""
import ast
import struct
import threading
import unittest
from types import SimpleNamespace
from pathlib import Path

from core.audio_meter import pcm16_level

ROOT = Path(__file__).resolve().parents[1]


class PcmMeterTests(unittest.TestCase):
    def test_silence_is_zero(self):
        self.assertEqual(pcm16_level(b"\x00\x00" * 1024), 0.0)
        self.assertEqual(pcm16_level(b""), 0.0)

    def test_louder_pcm_creates_stronger_signal(self):
        quiet = struct.pack("<h", 100) * 1024
        speech = struct.pack("<h", 5000) * 1024
        self.assertGreater(pcm16_level(speech), pcm16_level(quiet))
        self.assertGreater(pcm16_level(speech), 0.11)

    def test_clamped_and_odd_length_are_safe(self):
        loud = struct.pack("<h", 32767) * 200
        self.assertLessEqual(pcm16_level(loud), 1.0)
        self.assertGreater(pcm16_level(loud), 0.0)
        self.assertEqual(pcm16_level(b"\x7f"), 0.0)
        self.assertEqual(pcm16_level(None), 0.0)

    def test_buffer_views_are_supported(self):
        raw = struct.pack("<h", 3000) * 600
        self.assertEqual(pcm16_level(raw), pcm16_level(memoryview(raw)))


class VoiceHudWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = (ROOT / "ui.py").read_text(encoding="utf-8")
        cls.main = (ROOT / "main.py").read_text(encoding="utf-8")

    def test_input_is_real_pcm_not_random_animation(self):
        self.assertIn("from core.audio_meter          import pcm16_level", self.main)
        self.assertIn("pcm16_level(data)", self.main)
        self.assertIn("loop.call_soon_threadsafe(", self.main)
        self.assertIn('self._publish_mic_activity, data, "PC"', self.main)
        self.assertIn('self._publish_mic_activity(data, "PHONE")', self.main)
        self.assertIn("_mic_level_sig  = pyqtSignal(float, str)", self.ui)
        self.assertIn('def show_input_level(self, level: float, source: str = "PC")', self.ui)
        self.assertIn("self._mic_level_sig.connect(self._on_mic_level)", self.ui)

    def test_state_clear_and_real_mic_timeout(self):
        self.assertIn("def clear_input_level(self) -> None:", self.ui)
        self.assertIn("self.hud.clear_input_level()", self.ui)
        self.assertIn("(now - self._mic_last_packet) < 0.65", self.ui)
        self.assertIn("self._mic_level > 0.08", self.ui)
        self.assertIn("WAITING FOR MIC AUDIO", self.ui)
        self.assertIn("AUDIO DETECTED", self.ui)

    def test_existing_stream_and_cloud_provider_unchanged(self):
        self.assertIn("await self.session.send_realtime_input(media=msg)", self.main)
        self.assertIn('LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"', self.main)
        self.assertIn("enqueue_latest_audio(self.out_queue, chunk)", self.main)
        self.assertIn("self._tmr.start(33)", self.ui)
        self.assertIn("self.hud.speaking = (state == \"SPEAKING\")", self.ui)


class QtShutdownRaceTests(unittest.TestCase):
    """Execute EDITH's actual signal guard with fake Qt-like signals."""

    @classmethod
    def setUpClass(cls):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        edith_ui = next(node for node in tree.body
                        if isinstance(node, ast.ClassDef) and node.name == "EdithUI")
        method = next(node for node in edith_ui.body
                      if isinstance(node, ast.FunctionDef) and node.name == "_emit_if_open")
        module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
        namespace = {}
        exec(compile(module, str(ROOT / "ui.py"), "exec"), namespace)
        cls.emit_guard = staticmethod(namespace["_emit_if_open"])
        cls.main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.ui_source = source

    def _fake_ui(self, emit):
        return SimpleNamespace(
            _closed=threading.Event(),
            _win=SimpleNamespace(_mic_level_sig=SimpleNamespace(emit=emit)),
        )

    def test_live_window_publishes_mic_level(self):
        observed = []
        ui = self._fake_ui(lambda *args: observed.append(args))
        self.assertTrue(self.emit_guard(ui, "_mic_level_sig", 0.25, "PC"))
        self.assertEqual(observed, [(0.25, "PC")])
        self.assertFalse(ui._closed.is_set())

    def test_closed_window_silently_discards_late_audio(self):
        def should_not_emit(*args):
            self.fail("A closed QWidget must not receive audio signals")
        ui = self._fake_ui(should_not_emit)
        ui._closed.set()
        self.assertFalse(self.emit_guard(ui, "_mic_level_sig", 0.25, "PC"))

    def test_destroyed_window_race_is_handled_and_latched(self):
        called = []
        def deleted(*args):
            called.append(1)
            raise RuntimeError("wrapped C/C++ object of type MainWindow has been deleted")
        ui = self._fake_ui(deleted)
        self.assertFalse(self.emit_guard(ui, "_mic_level_sig", 0.25, "PC"))
        self.assertTrue(ui._closed.is_set())
        self.assertFalse(self.emit_guard(ui, "_mic_level_sig", 0.50, "PHONE"))
        self.assertEqual(called, [1], "Do not emit after a deleted Qt object is seen")

    def test_unrelated_runtime_errors_are_not_hidden(self):
        def other_failure(*args):
            raise RuntimeError("signal argument is invalid")
        ui = self._fake_ui(other_failure)
        with self.assertRaisesRegex(RuntimeError, "argument is invalid"):
            self.emit_guard(ui, "_mic_level_sig", 0.25, "PC")

    def test_audio_and_setup_honor_shutdown_without_touching_models(self):
        self.assertIn("if getattr(self.ui, \"closed\", False):", self.main_source)
        self.assertIn("if not ui.wait_for_api_key():", self.main_source)
        self.assertIn("self._app.aboutToQuit.connect(self._mark_closed)", self.ui_source)
        self.assertIn("self._win.destroyed.connect(self._mark_closed)", self.ui_source)
        self.assertIn('LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"', self.main_source)
        self.assertIn("from core.task_scheduler", self.main_source)


if __name__ == "__main__":
    unittest.main()
