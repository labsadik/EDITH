"""Portable hardware-inventory and device-bridge contracts."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from core.device_tools import DeviceToolService
from edith.platform.hardware import collect_hardware_inventory
from edith.platform.linux import LinuxController
from edith.platform.permissions import PermissionBroker


class HardwareInventoryTests(unittest.TestCase):
    def test_inventory_has_a_stable_cross_platform_shape_when_probes_fail(self):
        with patch("edith.platform.hardware.psutil.disk_partitions", return_value=[]), \
             patch("edith.platform.hardware.psutil.net_if_stats", return_value={}), \
             patch("edith.platform.hardware.psutil.net_if_addrs", return_value={}), \
             patch("edith.platform.hardware._audio_devices", return_value=[]):
            data = collect_hardware_inventory("Other")
        self.assertEqual(data["system"], "Other")
        for key in ("cpu", "memory", "storage", "network_adapters", "displays", "audio_devices", "usb", "graphics", "battery"):
            self.assertIn(key, data)

    def test_linux_inventory_uses_bounded_local_commands(self):
        commands = []
        def reader(argv, timeout=4):
            commands.append((argv, timeout))
            return "00:02.0 VGA compatible controller: Example GPU" if argv == ["lspci"] else ""
        with patch("edith.platform.hardware._linux_displays", return_value=[]), \
             patch("edith.platform.hardware._audio_devices", return_value=[]), \
             patch("edith.platform.hardware.shutil.which", return_value=None):
            data = collect_hardware_inventory("Linux", reader)
        self.assertEqual(data["graphics"], [{"name": "00:02.0 VGA compatible controller: Example GPU"}])
        self.assertIn((["lspci"], 4), commands)

    def test_controller_exposes_hardware_as_read_only_structured_results(self):
        controller = LinuxController(permissions=PermissionBroker(), audit=Mock())
        sample = {"displays": [{"name": "Main"}], "audio_devices": [{"name": "Speaker"}]}
        with patch.object(controller, "_hardware_snapshot", return_value=sample):
            self.assertEqual(controller.hardware_inventory()["data"], sample)
            self.assertEqual(controller.display_list()["data"], sample["displays"])
            self.assertEqual(controller.audio_devices()["data"], sample["audio_devices"])

    def test_device_bridge_allows_hardware_inventory_only_with_no_arguments(self):
        controller = Mock()
        controller.invoke.return_value = {"ok": True, "data": {"system": "Linux"}, "error": None, "unsupported": False}
        service = DeviceToolService(controller)
        response = service.execute({"operation": "hardware_inventory"})
        self.assertTrue(response["ok"])
        self.assertEqual(controller.invoke.call_args.args, ("hardware_inventory", {}))
        self.assertFalse(service.execute({"operation": "hardware_inventory", "arguments": {"extra": 1}})["ok"])


if __name__ == "__main__":
    unittest.main()
