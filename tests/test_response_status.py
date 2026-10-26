"""Execute actual runtime methods with fake session/audio events; no provider calls."""
import ast
import asyncio
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import Future
from core.narration_audio import SpeechBuffer
from core.live_audio import response_pcm


def method(name, **globals_):
    source = Path(__file__).resolve().parents[1] / 'main.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'EdithLive')
    fn = next(n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    scope = {'asyncio': asyncio, 'time': time, 'datetime': datetime,
             '_clean_transcript': lambda text: text.strip(), 'response_pcm':response_pcm, **globals_}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(source), 'exec'), scope)
    return scope[name]


class ResponseStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_transcript_then_turn_complete_updates_status(self):
        states = []
        transcript = SimpleNamespace(text='Hello')
        def response(input_text=None, done=False):
            return SimpleNamespace(data=None, tool_call=None, server_content=SimpleNamespace(
                input_transcription=input_text, output_transcription=None, turn_complete=done))
        async def receive():
            yield response(transcript)
            yield response(done=True)
            raise asyncio.CancelledError()
        obj = SimpleNamespace(session=SimpleNamespace(receive=receive), _is_speaking=False,
            _response_pending=False, _dashboard=None, _interrupted=False, _pending_vision=None,
            _vision_close_pending=False, _turn_done_event=asyncio.Event(), _session_log=[],
            _asst_name='EDITH', audio_in_queue=SpeechBuffer(),
            ui=SimpleNamespace(set_state=states.append, write_log=lambda text: None))
        with self.assertRaises(asyncio.CancelledError):
            await method('_receive_audio')(obj)
        self.assertEqual(states, ['THINKING', 'LISTENING'])
        self.assertFalse(obj._response_pending)

    def test_playback_pause_retains_pending_thinking_state(self):
        states = []
        obj = SimpleNamespace(_speaking_lock=threading.Lock(), _response_pending=True,
                              ui=SimpleNamespace(muted=False, set_state=states.append))
        call = method('set_speaking')
        call(obj, True)
        call(obj, False)
        obj._response_pending = False
        call(obj, False)
        self.assertEqual(states, ['SPEAKING', 'THINKING', 'LISTENING'])

    def test_failed_text_send_clears_pending_indicator_and_preserves_draft(self):
        states, restored = [], []
        future = Future()
        bridge = SimpleNamespace(run_coroutine_threadsafe=lambda *args: future)
        ui = SimpleNamespace(set_state=states.append, write_log=lambda text: None,
                             _win=SimpleNamespace(text_send_failed_signal=SimpleNamespace(emit=restored.append)))
        obj = SimpleNamespace(ui=ui, _loop=SimpleNamespace(is_running=lambda: True),
                              session=SimpleNamespace(send_client_content=lambda **kwargs: object()))
        self.assertTrue(method('_on_text_command', asyncio=bridge)(obj, 'Retain this'))
        self.assertTrue(obj._response_pending)
        future.set_exception(OSError('network unavailable'))
        self.assertFalse(obj._response_pending)
        self.assertEqual(states, ['THINKING', 'LISTENING'])
        self.assertEqual(restored, ['Retain this'])
