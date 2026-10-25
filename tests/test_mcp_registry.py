from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from core.mcp_registry import MCPRegistry, MCPServerSpec, MCPStdioClient
from core.plugin_loader import PluginRecord, PluginRegistry


ROOT = Path(__file__).resolve().parents[1]
STUB = ROOT / "tests" / "fixtures" / "mcp_stdio_stub.py"


class MCPRegistryTests(unittest.TestCase):
    def test_catalog_creates_disabled_toggleable_servers(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = MCPRegistry(Path(folder) / "servers.json", logger=lambda _msg: None)
            specs = registry.specs()
            self.assertEqual({item.id for item in specs}, {"gmail", "github", "filesystem"})
            self.assertFalse(registry.spec("gmail").enabled)
            self.assertTrue(registry.set_enabled("gmail", True))
            self.assertTrue(registry.spec("gmail").enabled)
            self.assertFalse(registry.set_enabled("missing", True))

    def test_stdio_client_initializes_lists_and_calls_a_server_tool(self):
        spec = MCPServerSpec(
            id="stub", name="Stub", description="test",
            command=(sys.executable, str(STUB)), enabled=True,
        )
        with MCPStdioClient(spec) as client:
            self.assertEqual(client.list_tools()[0]["name"], "echo")
            value = client.call_tool("echo", {"text": "hello"})
        self.assertEqual(value["content"][0]["text"], "hello")

    def test_registry_runs_configured_server_and_respects_its_toggle(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "servers.json"
            config.write_text(json.dumps({"servers": [{
                "id": "stub", "name": "Stub MCP", "description": "test",
                "command": [sys.executable, str(STUB)], "enabled": True,
            }]}), encoding="utf-8")
            registry = MCPRegistry(config, logger=lambda _msg: None)
            self.assertEqual(registry.list_tools("stub")[0]["name"], "echo")
            self.assertEqual(registry.call("stub", "echo", {"text": "EDITH"})["content"][0]["text"], "EDITH")
            registry.set_enabled("stub", False)
            with self.assertRaisesRegex(Exception, "OFF"):
                registry.list_tools("stub")

    def test_plugin_registry_hides_plugins_when_their_server_toggle_is_off(self):
        rec = PluginRecord(
            name="mcp_stub", description="test", valid=True,
            enabled_check=lambda: False,
        )
        registry = PluginRegistry({"mcp_stub": rec}, logger=lambda _msg: None)
        registry._all_records = [rec]
        self.assertEqual(registry.get_tool_declarations(), [])
        self.assertFalse(registry.list_for_ui()[0]["enabled"])


if __name__ == "__main__":
    unittest.main()
