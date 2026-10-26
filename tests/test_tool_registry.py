from __future__ import annotations

import unittest

from core.tool_registry import ToolRegistry


BUILTINS = [
    {"name": "shell_execute", "description": "shell", "parameters": {}},
    {"name": "system_status", "description": "status", "parameters": {}},
    {"name": "platform_system", "description": "device", "parameters": {}},
    {"name": "send_message", "description": "send", "parameters": {}},
]


class ToolRegistryTests(unittest.TestCase):
    def test_unifies_sources_without_leaking_policy_to_plugins(self):
        plugins = [
            {"name": "calendar_lookup", "description": "calendar", "parameters": {}},
            {"name": "mcp_gmail", "description": "mail", "parameters": {}},
        ]
        registry = ToolRegistry(BUILTINS, lambda: plugins)
        by_name = {item.name: item for item in registry.descriptors()}

        self.assertEqual(by_name["shell_execute"].source, "local_command")
        self.assertEqual(by_name["system_status"].source, "builtin")
        self.assertEqual(by_name["calendar_lookup"].source, "plugin")
        self.assertEqual(by_name["mcp_gmail"].source, "mcp")
        self.assertEqual(registry.policy("mcp_gmail"), (False, 0))

    def test_retry_and_fallback_are_only_for_declared_read_only_tool(self):
        registry = ToolRegistry(BUILTINS, lambda: [])
        self.assertEqual(registry.policy("system_status"), (True, 1))
        self.assertEqual(registry.policy("send_message"), (False, 0))
        self.assertEqual(registry.policy("unknown"), (False, 0))

        candidate = registry.fallback_for("system_status")
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.name, "platform_system")
        self.assertEqual(candidate.arguments, {"operation": "telemetry"})
        self.assertIsNone(registry.fallback_for("send_message"))

    def test_plugin_list_is_refreshed_for_live_toggle_changes(self):
        plugins = [{"name": "mcp_gmail", "description": "mail", "parameters": {}}]
        registry = ToolRegistry(BUILTINS, lambda: plugins)
        self.assertIn("mcp_gmail", {item["name"] for item in registry.declarations()})
        plugins.clear()
        self.assertNotIn("mcp_gmail", {item["name"] for item in registry.declarations()})


if __name__ == "__main__":
    unittest.main()
