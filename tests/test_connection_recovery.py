from __future__ import annotations

from pathlib import Path
import unittest

from core.action_activity import activity_outcome


ROOT = Path(__file__).resolve().parents[1]


class BrowserRecoveryTests(unittest.TestCase):
    def test_closed_context_is_discarded_and_relaunched_before_next_action(self):
        source = (ROOT / "actions" / "browser_control.py").read_text(encoding="utf-8")
        self.assertIn("async def _discard_context", source)
        self.assertIn("await self._discard_context()", source)
        self.assertIn("Target page, context or browser has been closed", source)

    def test_browser_context_failure_is_reported_as_an_error_not_success(self):
        text = "Browser error (go_to): Target page, context or browser has been closed"
        self.assertEqual(activity_outcome(text), "error")


class LiveRecoveryContractTests(unittest.TestCase):
    def test_live_disconnect_is_summarised_and_retried_without_duplicate_traceback(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("def _exception_summary", source)
        self.assertIn("Live session disconnected", source)
        self.assertIn("Gemini Live session disconnected; reconnecting automatically.", source)
        self.assertNotIn('traceback.print_exc()\n            raise', source)


if __name__ == "__main__":
    unittest.main()
