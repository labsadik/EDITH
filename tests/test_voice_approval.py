"""Exact, one-time approval binding and active-task input gate contracts."""
from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

from core.voice_approval import VoiceApprovalGate, is_interrupt_phrase


class VoiceApprovalGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_approval_resolves_only_the_current_request(self):
        gate = VoiceApprovalGate()
        request = gate.begin("file_controller", {"action": "delete", "path": "/tmp/a"})
        waiter = asyncio.create_task(gate.wait(request.token))
        await asyncio.sleep(0)
        self.assertIsNone(gate.observe("yes please"), "long/inferred consent must not authorize")
        self.assertTrue(gate.observe("confirm"))
        self.assertTrue(await waiter)
        self.assertIsNone(gate.pending)

    async def test_stale_or_wrong_action_reply_cannot_reuse_consent(self):
        gate = VoiceApprovalGate()
        first = gate.begin("shell_execute", {"command": "echo safe"})
        self.assertTrue(gate.cancel(first.token))
        self.assertIsNone(gate.observe("yes"))
        second = gate.begin("shell_execute", {"command": "rm -rf target"})
        self.assertNotEqual(first.token, second.token)
        waiter = asyncio.create_task(gate.wait(second.token))
        await asyncio.sleep(0)
        self.assertFalse(gate.observe("cancel"))
        self.assertFalse(await waiter)

    async def test_approval_fingerprint_is_bound_to_operation_arguments(self):
        gate = VoiceApprovalGate()
        one = gate.begin("file_controller", {"action": "delete", "path": "/tmp/a"})
        gate.cancel(one.token)
        two = gate.begin("file_controller", {"action": "delete", "path": "/tmp/b"})
        self.assertNotEqual(one.fingerprint, two.fingerprint)

    def test_only_narrow_stop_phrases_can_interrupt_busy_work(self):
        self.assertTrue(is_interrupt_phrase("থেমে যাও"))
        self.assertTrue(is_interrupt_phrase("stop now"))
        self.assertFalse(is_interrupt_phrase("can you stop after this"))


class VoiceApprovalIntegrationContracts(unittest.TestCase):
    def test_runtime_blocks_competing_input_and_has_no_approval_prompt(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "main.py").read_text(encoding="utf-8")
        ui = (root / "ui.py").read_text(encoding="utf-8")
        self.assertIn("self._task_input_locked = True", main)
        self.assertIn("self._handle_busy_input", main)
        self.assertIn("new action was not queued", main)
        self.assertNotIn("await self._request_voice_approval", main)
        self.assertNotIn("self.ui.confirm_sensitive_action", main)
        self.assertIn('self.ui.write_log(f"ACTIVITY RUNNING: {activity_label}")', main)
        self.assertIn('"WORKING"', ui)


if __name__ == "__main__":
    unittest.main()

