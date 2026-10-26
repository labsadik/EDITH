"""Cross-platform EDITH diagnostics and real async audio failure regressions."""
import ast
import asyncio
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.hardware_check import audio_compatibility, desktop_compatibility, report
from core.audio_meter import pcm16_level
from core.narration_audio import SpeechBuffer, SpeechPlayer

ROOT = Path(__file__).resolve().parents[1]


class HardwareCompatibilityTests(unittest.TestCase):
    def test_reports_os_desktop_limitations_without_assuming_every_os_is_supported(self):
        self.assertIn("Windows", desktop_compatibility("Windows", {}))
        self.assertIn("macOS", desktop_compatibility("Darwin", {}))
        self.assertIn("Wayland", desktop_compatibility("Linux", {"WAYLAND_DISPLAY": "wayland-0"}))
        self.assertIn("X11", desktop_compatibility("Linux", {"DISPLAY": ":0"}))
        self.assertIn("no active graphical display", desktop_compatibility("Linux", {}))
        self.assertIn("not guaranteed", desktop_compatibility("FreeBSD", {}))

    def test_checks_actual_pcm_rates_without_opening_audio_streams(self):
        calls = []

        class FakeSound:
            def query_devices(self, *, kind):
                calls.append(("query", kind))
                return {"default_samplerate": 48000}

            def check_input_settings(self, **kwargs):
                calls.append(("input", kwargs["samplerate"]))

            def check_output_settings(self, **kwargs):
                calls.append(("output", kwargs["samplerate"]))

        statuses = audio_compatibility(FakeSound())
        self.assertEqual(statuses["microphone"], "ready: mono PCM16 at 16000 Hz")
        self.assertEqual(statuses["speaker"], "ready: mono PCM16 at 24000 Hz")
        self.assertEqual(calls, [
            ("query", "input"), ("input", 16000),
            ("query", "output"), ("output", 24000),
        ])

    def test_missing_hardware_and_unsupported_rates_are_not_falsely_ready(self):
        class FakeSound:
            def query_devices(self, *, kind):
                if kind == "input":
                    raise OSError("No input device")
                return {"default_samplerate": 48000}

            def check_output_settings(self, **kwargs):
                raise ValueError("Unsupported 24000 Hz")

        statuses = audio_compatibility(FakeSound())
        self.assertIn("unavailable", statuses["microphone"])
        self.assertIn("unsupported", statuses["speaker"])
        self.assertNotIn("ready:", " ".join(statuses.values()))

    def test_report_contains_no_config_or_device_identifiers(self):
        with patch("core.hardware_check.audio_compatibility", return_value={
            "microphone": "unavailable", "speaker": "ready"
        }):
            data = report()
        self.assertEqual(data["product"], "EDITH")
        self.assertIn("logical_cpu_count", data)
        self.assertNotIn("gemini_api_key", str(data))
        self.assertNotIn("llm_url", str(data))
        self.assertNotIn("device_name", str(data))


def _audio_method(name: str, fake_sound: object):
    """Extract a real EDITH coroutine without importing Qt or PortAudio."""
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    live = next(node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "EdithLive")
    target = next(node for node in live.body
                  if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[target], type_ignores=[]))
    scope = {
        "asyncio": asyncio,
        "sd": fake_sound,
        "SEND_SAMPLE_RATE": 16000,
        "RECEIVE_SAMPLE_RATE": 24000,
        "CHANNELS": 1,
        "CHUNK_SIZE": 1024,
        "pcm16_level": pcm16_level,
        "SpeechPlayer": SpeechPlayer,
    }
    exec(compile(module, str(ROOT / "main.py"), "exec"), scope)
    return scope[name]


class AudioHardwareRecoveryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _failing_stream(**kwargs):
        raise OSError("Default audio device disconnected")

    async def _assert_survives_missing_device(self, method: str, sound: object):
        logs: list[str] = []
        ui = SimpleNamespace(write_log=logs.append, muted=False, show_output_level=lambda level: None)
        edith = SimpleNamespace(
            ui=ui,
            _speaking_lock=threading.Lock(),
            _is_speaking=False,
            _phone_active=False,
            _last_mic_meter_at=0.0,
            audio_in_queue=SpeechBuffer(),
            _interrupted=False,
            _turn_done_event=asyncio.Event(),
            set_speaking=lambda value: None,
        )
        function = _audio_method(method, sound)
        task = asyncio.create_task(function(edith))
        try:
            for _ in range(50):
                if logs:
                    break
                await asyncio.sleep(0.005)
            self.assertTrue(logs, "A missing audio device should be reported")
            self.assertFalse(task.done(), "Audio failure must not crash its task")
            self.assertIn("remain available", logs[0])
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_missing_microphone_does_not_crash_live_session(self):
        await self._assert_survives_missing_device(
            "_listen_audio", SimpleNamespace(InputStream=self._failing_stream)
        )

    async def test_missing_speaker_does_not_crash_live_session(self):
        await self._assert_survives_missing_device(
            "_play_audio", SimpleNamespace(RawOutputStream=self._failing_stream)
        )

    async def test_real_playback_worker_publishes_pcm_level_and_drains(self):
        import struct
        import time
        written, levels, speaking = [], [], []
        class Stream:
            def start(self): pass
            def stop(self): pass
            def close(self): pass
            def abort(self): pass
            def write(self, data):
                written.append(data)
                time.sleep(.06)
                return False
        chunk = struct.pack('<h', 6000) * 1200
        queue = SpeechBuffer()
        queue.put_nowait(chunk)
        queue.finish_turn()
        obj = SimpleNamespace(audio_in_queue=queue, _turn_done_event=asyncio.Event(),
            _interrupted=False,
            set_speaking=speaking.append,
            ui=SimpleNamespace(show_output_level=levels.append, write_log=lambda line: None))
        call = _audio_method('_play_audio', SimpleNamespace(RawOutputStream=lambda **kwargs: Stream()))
        task = asyncio.create_task(call(obj))
        try:
            for _ in range(100):
                if written and speaking == [True, False]:
                    break
                await asyncio.sleep(.01)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(written, [chunk])
        self.assertIn(pcm16_level(chunk), levels)
        self.assertEqual(levels[-1], 0)
        self.assertEqual(speaking[:2], [True, False])
        self.assertIsNone(obj._speech_player)


if __name__ == "__main__":
    unittest.main()

