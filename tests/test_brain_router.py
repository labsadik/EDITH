"""All non-voice text reasoning is routed to the single Powerful Brain."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from core import brain_router


class BrainRouterTests(unittest.TestCase):
    def test_legacy_main_and_specialist_roles_resolve_to_powerful(self):
        for role in ("main", "powerful", "software_development", "device_security", "smart_network", None):
            self.assertEqual(brain_router.resolve_brain_profile(role), "powerful")

    def test_audio_transport_is_not_misrouted_to_text_brain(self):
        for role in ("voice", "audio", "gemini_live"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                brain_router.resolve_brain_profile(role)

    def test_text_and_tool_calls_use_powerful_profile(self):
        with patch("core.llm_client.call_llm_text", return_value="text result") as call_text:
            value = brain_router.call_brain_text("plan a project", workload="software_development")
        self.assertEqual(value, "text result")
        self.assertEqual(call_text.call_args.kwargs["profile"], "powerful")

        with patch("core.llm_client.call_llm", return_value={"content": "ok", "tool_calls": []}) as call:
            value = brain_router.call_brain([{"role": "user", "content": "hello"}])
        self.assertEqual(value["content"], "ok")
        self.assertEqual(call.call_args.kwargs["profile"], "powerful")


if __name__ == "__main__":
    unittest.main()
