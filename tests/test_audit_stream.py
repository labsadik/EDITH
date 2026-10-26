"""Redacted audit receipts and Activity Log streaming contracts."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

from edith.platform.audit import AuditLog, redact, register_secret


class AuditStreamTests(unittest.TestCase):
    def test_audit_redacts_secret_fields_and_registered_values(self):
        secret = "sk-test-never-display-123456"
        register_secret(secret)
        entries = []
        with tempfile.TemporaryDirectory() as folder:
            audit = AuditLog(Path(folder) / "actions.jsonl", listener=entries.append)
            try:
                audit.write(
                    "agent", "tool.finish", {
                        "api_key": secret,
                        "command": f"token={secret}",
                        "message_text": "ordinary payload",
                    }, 2, {"ok": True, "result": "done"}
                )
            finally:
                for handler in audit._logger.handlers if audit._logger else []:
                    handler.close()
        self.assertEqual(len(entries), 1)
        rendered = repr(entries[0])
        self.assertNotIn(secret, rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_listener_receives_structured_redacted_entry(self):
        listener = Mock()
        with tempfile.TemporaryDirectory() as folder:
            audit = AuditLog(Path(folder) / "actions.jsonl", listener=listener)
            try:
                audit.write("agent", "tool.start", {"text": "x"}, 2, {"ok": None})
            finally:
                for handler in audit._logger.handlers if audit._logger else []:
                    handler.close()
        entry = listener.call_args.args[0]
        self.assertEqual(entry["operation"], "tool.start")
        self.assertEqual(entry["tier"], 2)
        self.assertIsNone(entry["result"]["ok"])


class AuditWiringContractTests(unittest.TestCase):
    def test_runtime_wires_platform_and_dispatcher_audit_to_activity_log(self):
        root = Path(__file__).resolve().parents[1]
        execution = (root / "core" / "execution.py").read_text(encoding="utf-8")
        main = (root / "main.py").read_text(encoding="utf-8")
        self.assertIn("SERVICE.audit.listener=_audit_listener", execution)
        self.assertIn("SERVICE.controller.audit.listener=_audit_listener", execution)
        self.assertIn('f"AUDIT {operation} · "', execution)
        self.assertIn("tool.{phase}", main)
        self.assertIn("safe_args = redact", main)


if __name__ == "__main__":
    unittest.main()
