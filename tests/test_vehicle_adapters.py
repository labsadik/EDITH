from __future__ import annotations

import unittest

from edith.special_devices.vehicle import (
    AuthorizedOEMVehicleAdapter,
    VehicleAdapterRegistry,
    VehicleSimulatorAdapter,
)


class VehicleAdapterTests(unittest.TestCase):
    def test_simulator_is_explicit_and_never_reports_a_real_connection(self):
        simulator = VehicleSimulatorAdapter()
        capabilities = simulator.capabilities()
        self.assertTrue(capabilities["simulator"])
        self.assertIn("No physical vehicle connection", capabilities["note"])
        self.assertFalse(simulator.invoke("simulate_drive", {"speed_kph": 20})["ok"])

    def test_simulator_state_transitions_are_bounded(self):
        simulator = VehicleSimulatorAdapter()
        self.assertTrue(simulator.invoke("simulate_ignition", {"enabled": True})["ok"])
        moving = simulator.invoke("simulate_drive", {"speed_kph": 55})
        self.assertTrue(moving["ok"])
        self.assertEqual(moving["data"]["gear"], "drive")
        self.assertEqual(moving["data"]["speed_kph"], 55.0)
        self.assertFalse(simulator.invoke("simulate_drive", {"speed_kph": 131})["ok"])
        stopped = simulator.invoke("simulate_stop")
        self.assertEqual(stopped["data"]["speed_kph"], 0.0)

    def test_oem_base_never_sends_a_physical_command(self):
        adapter = AuthorizedOEMVehicleAdapter("oem_demo", "OEM demo", authorised=True)
        result = adapter.invoke("drive", {"destination": "anywhere"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["unsupported"])
        self.assertIn("no physical vehicle command", result["error"])

    def test_registry_returns_structured_unknown_adapter_failure(self):
        registry = VehicleAdapterRegistry()
        result = registry.invoke("missing", "status")
        self.assertEqual(set(result), {"ok", "data", "error", "unsupported"})
        self.assertTrue(result["unsupported"])


if __name__ == "__main__":
    unittest.main()
