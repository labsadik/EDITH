"""Hands-free tool execution and stable speaker-echo/voice preferences."""
import ast
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock

from core.voice_intent import requested_voice_mode
from edith.platform.permissions import PermissionBroker


ROOT = Path(__file__).resolve().parents[1]


def main_method(name):
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "EdithLive")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {"time": time}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "main.py", "exec"), namespace)
    return namespace[name]


class HandsFreeVoiceTests(unittest.TestCase):
    def test_runtime_broker_keeps_tiers_and_interrupt_without_prompt(self):
        prompt = Mock(return_value=False)
        broker = PermissionBroker(confirmer=prompt, settings={"unattended": True})
        self.assertEqual(broker.authorize("shell", {"command": "echo hi"}), 2)
        self.assertEqual(broker.authorize("power", {"action": "sleep"}), 3)
        prompt.assert_not_called()
        self.assertEqual(broker.tier("power", {}), 3)

    def test_model_cannot_switch_voice_without_recent_direct_request(self):
        gate = main_method("_model_voice_change_allowed")
        class State:
            _recent_voice_intent = None
        state = State()
        self.assertFalse(gate(state, "male"))
        state._recent_voice_intent = ("female", time.monotonic())
        self.assertFalse(gate(state, "male"))
        state._recent_voice_intent = ("male", time.monotonic() - 50)
        self.assertFalse(gate(state, "male"))
        state._recent_voice_intent = ("male", time.monotonic())
        self.assertTrue(gate(state, "male"))
        self.assertFalse(gate(state, "male"))

    def test_voice_request_requires_an_instruction(self):
        self.assertEqual(requested_voice_mode("Switch to a male voice"), "male")
        self.assertEqual(requested_voice_mode("male voice please"), "male")
        self.assertEqual(requested_voice_mode("মেয়েদের কণ্ঠে কথা বলো"), "female")
        self.assertEqual(requested_voice_mode("মেয়েদের ভয়েস"), "female")
        self.assertIsNone(requested_voice_mode("Why did the voice switch to another place?"))
        self.assertIsNone(requested_voice_mode("What are the male voice options?"))

    def test_asr_variant_turn_into_female_is_a_direct_voice_request(self):
        self.assertEqual(requested_voice_mode("Turn into female blessings"), "female")

    def test_explicit_voice_change_is_saved_even_when_live_is_offline(self):
        handler = main_method("_on_text_command")
        class State:
            _loop = None
            session = None
            ui = Mock()
            _request_voice_mode_from_ui = Mock()
        state = State()
        self.assertTrue(handler(state, "Turn into female blessings"))
        state._request_voice_mode_from_ui.assert_called_once_with("female")
        state.ui.write_log.assert_not_called()

    def test_microphone_gate_covers_device_playback_and_tail(self):
        gate = main_method("_mic_can_send")
        class State:
            _is_speaking = False
            _speaking_lock = threading.Lock()
            _speech_player = None
            _mic_resume_at = 0.
        state = State()
        self.assertTrue(gate(state))
        state._speech_player = Mock(snapshot=lambda: {"playing": True})
        self.assertFalse(gate(state))
        state._speech_player = Mock(snapshot=lambda: {"playing": False})
        state._mic_resume_at = time.monotonic() + 1
        self.assertFalse(gate(state))


if __name__ == "__main__":
    unittest.main()
