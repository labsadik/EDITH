import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from core.live_audio import response_pcm

class LiveAudioPartsTests(unittest.TestCase):
    def test_mixed_thought_text_and_pcm_are_consumed_without_data_property(self):
        class Response:
            @property
            def data(self):
                raise AssertionError('SDK convenience accessor must not be called')
        response=Response()
        response.server_content=NS(model_turn=NS(parts=[
            NS(text='private thought',thought=True), NS(text='narration'),
            NS(inline_data=NS(mime_type='audio/pcm;rate=24000',data=b'12')),
            NS(inline_data=NS(mime_type='image/png',data=b'ignore')),
            NS(inline_data=NS(mime_type='audio/pcm',data=b'34'))]))
        self.assertEqual(response_pcm(response),b'1234')
    def test_text_only_empty_and_legacy_adapter_events(self):
        self.assertEqual(response_pcm(NS(server_content=NS(model_turn=NS(parts=[NS(text='text')])))),b'')
        self.assertEqual(response_pcm(NS(data=b'pcm',server_content=None)),b'pcm')
        self.assertEqual(response_pcm(NS(server_content=None)),b'')
    def test_automation_imports_are_deferred_until_after_qt_creation(self):
        source=Path(__file__).resolve().parents[1]/'main.py'
        tree=ast.parse(source.read_text())
        self.assertFalse(any(isinstance(n,ast.ImportFrom) and str(n.module).startswith('actions.') for n in tree.body))
        load=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_load_action_modules')
        self.assertTrue(any(isinstance(n,ast.ImportFrom) and str(n.module).startswith('actions.') for n in load.body))
