"""Backend permission-floor regressions for legacy tool dispatch."""
import unittest
from unittest.mock import Mock

from core.execution import ExecutionService
from edith.platform.permissions import (
    ActionCancelled, ExecutionContext, CURRENT, PermissionBroker, PermissionDenied,
    tool_tier,
)


class PermissionFloorTests(unittest.TestCase):
    def test_sensitive_tools_have_backend_floors_independent_of_ui_reason(self):
        self.assertEqual(tool_tier("shell_execute", {"command": "echo hi"}), 2)
        self.assertEqual(tool_tier("shell_execute", {"command": "shutdown /s"}), 3)
        self.assertEqual(tool_tier("shutdown_edith", {}), 3)
        self.assertEqual(tool_tier("file_controller", {"action": "read"}), 0)
        self.assertEqual(tool_tier("file_controller", {"action": "write"}), 2)

    def test_model_flags_cannot_approve_without_local_confirmer(self):
        broker = PermissionBroker(confirmer=None)
        with self.assertRaises(PermissionDenied):
            broker.authorize("shell", {"command": "echo hi", "confirmed": True})

    def test_dispatcher_approval_can_cross_thread_but_only_as_internal_context(self):
        broker = PermissionBroker(confirmer=None)
        with broker.approved_context("shell"):
            self.assertEqual(broker.authorize("shell", {"command": "echo hi"}), 2)
        with self.assertRaises(PermissionDenied):
            broker.authorize("shell", {"command": "echo hi"})

    def test_interrupt_invalidates_preapproved_worker_context(self):
        broker = PermissionBroker(confirmer=None)
        token = CURRENT.set(ExecutionContext("test", broker.generation))
        try:
            with broker.approved_context("shell"):
                broker.cancel_all()
                with self.assertRaises(ActionCancelled):
                    broker.authorize("shell", {"command": "echo hi"})
        finally:
            CURRENT.reset(token)


class MainDispatchContractTests(unittest.TestCase):
    def test_main_keeps_audited_tiers_without_a_dispatcher_dialog(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn("backend_tier = tool_tier(name, args)", text)
        self.assertIn("EXECUTION.broker.authorize(name, args, minimum=backend_tier)", text)
        self.assertIn("approved_context(*approved_ops)", text)
        self.assertIn('self.ui.write_log(f"ACTIVITY RUNNING: {activity_label}")', text)


if __name__ == "__main__":
    unittest.main()
