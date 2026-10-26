"""Tests for the narrowed local-device bridge (no remote/security tooling)."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from core.device_tools import DeviceToolService, format_device_result
from edith.platform.linux import LinuxController
from edith.platform.permissions import PermissionBroker


class _Controller:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"ok": True, "data": {"answer": "ok"}, "error": None, "unsupported": False}

    def invoke(self, operation, arguments):
        self.calls.append((operation, arguments))
        return self.response


class DeviceToolTests(unittest.TestCase):
    def test_read_only_operation_is_forwarded_to_the_platform_controller(self):
        controller = _Controller({"ok": True, "data": {"os": "Linux"}, "error": None, "unsupported": False})
        receipt = DeviceToolService(controller).execute({"operation": "system_info"})
        self.assertTrue(receipt["ok"])
        self.assertEqual(controller.calls, [("system_info", {})])
        self.assertIn('"Linux"', format_device_result(receipt))

    def test_hardware_inventory_and_device_lists_are_declared_read_only_operations(self):
        controller = _Controller()
        service = DeviceToolService(controller)
        for operation in ("hardware_inventory", "display_list", "audio_devices"):
            with self.subTest(operation=operation):
                self.assertTrue(service.execute({"operation": operation})["ok"])
        self.assertEqual([name for name, _ in controller.calls], ["hardware_inventory", "display_list", "audio_devices"])

    def test_controls_are_validated_before_native_invocation(self):
        controller = _Controller()
        service = DeviceToolService(controller)
        self.assertFalse(service.execute({"operation": "volume", "arguments": {"value": 101}})["ok"])
        self.assertFalse(service.execute({"operation": "process_kill", "arguments": {"pid": "nope"}})["ok"])
        self.assertFalse(service.execute({"operation": "power", "arguments": {"action": "format"}})["ok"])
        self.assertEqual(controller.calls, [])

    def test_generic_shell_remote_and_binary_capture_are_not_exposed(self):
        controller = _Controller()
        service = DeviceToolService(controller)
        for operation in ("shell", "remote_connect", "network_scan", "screenshot"):
            with self.subTest(operation=operation):
                receipt = service.execute({"operation": operation})
                self.assertFalse(receipt["ok"])
                self.assertIn("Unsupported", receipt["error"])
        self.assertEqual(controller.calls, [])

    def test_result_is_bounded_and_binary_like_data_is_omitted(self):
        controller = _Controller({
            "ok": True,
            "data": {"base64": "x" * 50_000, "windows": list(range(200))},
            "error": None,
            "unsupported": False,
        })
        receipt = DeviceToolService(controller).execute({"operation": "window_list"})
        self.assertIn("omitted binary payload", receipt["data"]["base64"])
        self.assertEqual(len(receipt["data"]["windows"]), 120)

    def test_sensitive_control_keeps_backend_confirmation_boundary(self):
        broker = PermissionBroker(confirmer=lambda *_: False)
        controller = LinuxController(permissions=broker, audit=Mock())
        service = DeviceToolService(controller)
        with patch.object(controller, "_op_volume") as volume:
            denied = service.execute({"operation": "volume", "arguments": {"value": 42}})
        self.assertFalse(denied["ok"])
        volume.assert_not_called()

        with patch.object(controller, "_op_volume", return_value={"percent": 42}) as volume:
            with broker.approved_context("volume"):
                approved = service.execute({"operation": "volume", "arguments": {"value": 42}})
        self.assertTrue(approved["ok"])
        volume.assert_called_once_with(value=42)

    def test_main_declares_and_routes_the_shared_device_bridge(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn('"name": "platform_system"', text)
        self.assertIn("self._device_tools.execute", text)
        self.assertIn("approved_ops.add(str(args.get(\"operation\") or \"\"))", text)


if __name__ == "__main__":
    unittest.main()

