"""Device Security and Smart Network are read-only diagnostics."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from agents import device_security, smart_network


class DeviceSecurityAgentTests(unittest.TestCase):
    def test_windows_audit_uses_only_fixed_read_only_commands(self):
        calls = []

        def fake(argv, timeout=5.0):
            calls.append(argv)
            return {"available": True, "exit_code": 0, "output": "diagnostic"}

        with patch.object(device_security.platform, "system", return_value="Windows"), patch.object(
            device_security, "_read_command", side_effect=fake
        ):
            result = device_security.security_posture()
        self.assertEqual(result["agent"], "device_security")
        self.assertEqual(result["version"], device_security.AGENT_VERSION)
        self.assertIn("firewall", result["checks"])
        self.assertIn("defender", result["checks"])
        self.assertTrue(all(command[0] == "powershell" for command in calls))
        self.assertTrue(all("Set-" not in " ".join(command) for command in calls))

    def test_security_audit_never_claims_changes_were_made(self):
        with patch.object(device_security.platform, "system", return_value="Unknown"), patch.object(
            device_security, "_read_command", return_value={"available": False, "reason": "unknown"}
        ):
            result = device_security.security_posture()
        self.assertEqual(result["mode"], "read-only audit")
        self.assertIn("No settings were changed", result["note"])


class SmartNetworkAgentTests(unittest.TestCase):
    def test_neighbor_inventory_is_passive_and_cannot_control_devices(self):
        with patch.object(smart_network, "_neighbors", return_value=([{
            "ip": "192.168.1.12", "mac": "00:11:22:33:44:55", "source": "OS neighbor cache"
        }], "arp")) , patch.object(
            smart_network, "_interfaces", return_value={"wifi": {"available": True}}
        ):
            result = smart_network.discover_local_devices()
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["active_scan"])
        self.assertFalse(result["control_available"])
        self.assertIn("authenticated pairing", result["control_note"])
        self.assertIn("interfaces", result)

    def test_private_address_filter_rejects_public_and_invalid_records(self):
        output = """? (192.168.1.10) at 00:11:22:33:44:55 on en0
? (8.8.8.8) at 00:11:22:33:44:66 on en0
? (not-an-ip) at 00:11:22:33:44:77 on en0
"""
        with patch.object(smart_network.platform, "system", return_value="Darwin"), patch.object(
            smart_network, "_run_fixed",
            return_value={"available": True, "output": output},
        ):
            devices, source = smart_network._neighbors()
        self.assertEqual(source, "ip")
        self.assertEqual([item["ip"] for item in devices], ["192.168.1.10"])


if __name__ == "__main__":
    unittest.main()
