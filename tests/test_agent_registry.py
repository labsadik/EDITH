"""Versioned agent catalog, default enablement and persisted toggles."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import agent_registry


class AgentRegistryTests(unittest.TestCase):
    def test_every_builtin_agent_has_semver_and_is_enabled_by_default(self):
        agents = agent_registry.list_agents()
        self.assertGreaterEqual(len(agents), 8)
        for agent in agents:
            pieces = agent["version"].split(".")
            self.assertEqual(len(pieces), 3)
            self.assertTrue(all(piece.isdigit() for piece in pieces))
            self.assertTrue(agent["enabled"], agent["id"])
        ids = {agent["id"] for agent in agents}
        self.assertTrue({
            "orchestrator", "software_development", "device_security",
            "smart_network", "research", "browser_computer",
            "file_workspace", "system_monitor",
        }.issubset(ids))

    def test_toggle_is_persisted_without_modifying_the_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "agents.json"
            with patch.object(agent_registry, "CONFIG_PATH", config):
                before = agent_registry.get_agent("software_development")
                self.assertTrue(before["enabled"])
                disabled = agent_registry.set_agent_enabled("software_development", False)
                self.assertFalse(disabled["enabled"])
                self.assertEqual(disabled["status"], "disabled")
                self.assertFalse(agent_registry.is_agent_enabled("software_development"))
                self.assertEqual(
                    json.loads(config.read_text(encoding="utf-8"))["enabled"]["software_development"],
                    False,
                )
                enabled = agent_registry.set_agent_enabled("software_development", True)
                self.assertTrue(enabled["enabled"])

    def test_unknown_agents_are_rejected(self):
        with self.assertRaises(KeyError):
            agent_registry.set_agent_enabled("unknown_agent", False)

    def test_disabled_specialist_tools_are_removed_but_manager_stays(self):
        declarations = [
            {"name": "agent_manager"},
            {"name": "dev_agent"},
            {"name": "device_security"},
            {"name": "web_search"},
        ]
        with tempfile.TemporaryDirectory() as folder, patch.object(
            agent_registry, "CONFIG_PATH", Path(folder) / "agents.json"
        ):
            agent_registry.set_agent_enabled("software_development", False)
            filtered = agent_registry.filter_tool_declarations(declarations)
        names = [item["name"] for item in filtered]
        self.assertIn("agent_manager", names)
        self.assertNotIn("dev_agent", names)
        self.assertIn("device_security", names)
        self.assertIn("web_search", names)

    def test_catalog_contains_exact_agent_versions(self):
        catalog = agent_registry.format_agent_catalog()
        self.assertIn("software_development", catalog)
        self.assertIn("v1.0.0", catalog)
        self.assertIn("device_security", catalog)
        self.assertIn("smart_network", catalog)


if __name__ == "__main__":
    unittest.main()
