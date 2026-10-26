"""Phase 2: low-latency queue and dual-provider regression tests.

No network connections, microphone, cloud credentials or GUI are used here.
"""
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from core import llm_client
from core.realtime_audio import enqueue_latest_audio


class RealtimeQueueTests(unittest.TestCase):
    def test_audio_is_added_in_order(self):
        queue = asyncio.Queue(maxsize=2)
        self.assertTrue(enqueue_latest_audio(queue, b"one"))
        self.assertTrue(enqueue_latest_audio(queue, b"two"))
        self.assertEqual(queue.get_nowait(), b"one")
        self.assertEqual(queue.get_nowait(), b"two")

    def test_stale_audio_is_replaced_when_full(self):
        queue = asyncio.Queue(maxsize=2)
        enqueue_latest_audio(queue, b"old-1")
        enqueue_latest_audio(queue, b"old-2")
        self.assertTrue(enqueue_latest_audio(queue, b"new"))
        self.assertEqual(queue.qsize(), 2)
        self.assertEqual(queue.get_nowait(), b"old-2")
        self.assertEqual(queue.get_nowait(), b"new")

    def test_missing_queue_is_safe(self):
        self.assertFalse(enqueue_latest_audio(None, b"test"))


class LocalAgentTokenBudgetTests(unittest.TestCase):
    def _response(self, provider):
        response = Mock()
        response.json.return_value = (
            {"choices": [{"message": {"content": " Answer ", "tool_calls": []}}]}
            if provider == "openai"
            else {"message": {"content": " Answer ", "tool_calls": []}}
        )
        return response

    def _assert_text_budget(self, provider, endpoint, option_key):
        with (
            patch.object(llm_client, "get_llm_provider", return_value=provider),
            patch.object(llm_client, "get_llm_settings", return_value=("http://localhost:9999", "test-model")),
            patch.object(llm_client.requests, "post", return_value=self._response(provider)) as post,
        ):
            actual = llm_client.call_llm_text("test question", system="test system")
            self.assertEqual(actual, "Answer")
            args, kwargs = post.call_args
            self.assertEqual(args[0], "http://localhost:9999" + endpoint)
            self.assertEqual(kwargs["json"]["model"], "test-model")
            self.assertEqual(kwargs["json"][option_key] if provider == "openai"
                             else kwargs["json"]["options"][option_key], 600)
            self.assertEqual(kwargs["json"]["messages"][0]["role"], "system")

    def test_ollama_agent_keeps_600_token_budget(self):
        self._assert_text_budget("ollama", "/api/chat", "num_predict")

    def test_openai_compatible_agent_keeps_600_token_budget(self):
        self._assert_text_budget("openai", "/v1/chat/completions", "max_tokens")

    def test_short_chat_keeps_150_token_default(self):
        with (
            patch.object(llm_client, "get_llm_provider", return_value="ollama"),
            patch.object(llm_client, "get_llm_settings", return_value=("http://localhost:11434", "test")),
            patch.object(llm_client.requests, "post", return_value=self._response("ollama")) as post,
        ):
            llm_client.call_llm([{"role": "user", "content": "hi"}])
            self.assertEqual(post.call_args.kwargs["json"]["options"]["num_predict"], 150)

    def test_explicit_model_override_works_with_openai_backend(self):
        with (
            patch.object(llm_client, "get_llm_provider", return_value="openai"),
            patch.object(llm_client, "get_llm_settings", return_value=("http://localhost:1234", "default-model")),
            patch.object(llm_client.requests, "post", return_value=self._response("openai")) as post,
        ):
            self.assertEqual(llm_client.call_llm_text("hello", model="another-model"), "Answer")
            self.assertEqual(post.call_args.kwargs["json"]["model"], "another-model")
            self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 600)

    def test_llm_streaming_remains_available_for_both_providers(self):
        with (
            patch.object(llm_client, "get_llm_provider", return_value="openai"),
            patch.object(llm_client, "_stream_openai", return_value=iter([
                {"type": "sentence", "text": "Hello."},
                {"type": "done", "content": "Hello.", "tool_calls": []},
            ])) as stream,
        ):
            events = list(llm_client.call_llm_stream([{"role": "user", "content": "Hi"}]))
            self.assertEqual(events[0]["type"], "sentence")
            self.assertEqual(events[-1]["type"], "done")
            stream.assert_called_once()


class FastResponseWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.main = (root / "main.py").read_text(encoding="utf-8")
        cls.ui = (root / "ui.py").read_text(encoding="utf-8")

    def test_live_api_and_local_llm_remain_separate(self):
        self.assertIn("client.aio.live.connect(model=LIVE_MODEL, config=config)", self.main)
        self.assertIn("from core.realtime_audio      import enqueue_latest_audio", self.main)
        self.assertIn("self.out_queue        = asyncio.Queue(maxsize=32)", self.main)

    def test_connection_timing_and_nonblocking_input(self):
        self.assertIn("config = await asyncio.to_thread(self._build_config)", self.main)
        self.assertIn("Gemini Live first audio after text request", self.main)
        self.assertIn("self.on_text_command(txt)", self.ui)
        self.assertNotIn("threading.Thread(target=self.on_text_command", self.ui)


if __name__ == "__main__":
    unittest.main()
