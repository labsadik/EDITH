"""Durability and recovery coverage for EDITH's local long-term memory."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from memory import memory_manager as memory


class MemoryDurabilityTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self._previous_path = memory.MEMORY_PATH
        memory.MEMORY_PATH = Path(self._folder.name) / "long_term.json"

    def tearDown(self):
        memory.MEMORY_PATH = self._previous_path
        self._folder.cleanup()

    def test_legacy_document_is_normalised_without_losing_tool_data(self):
        memory.MEMORY_PATH.write_text(json.dumps({
            "identity": {"name": {"value": "Ada"}},
            "monitor_state": {"news": {"value": "kept"}},
        }), encoding="utf-8")

        loaded = memory.load_memory()

        self.assertEqual(loaded["identity"]["name"]["value"], "Ada")
        self.assertEqual(loaded["monitor_state"]["news"]["value"], "kept")
        self.assertTrue(all(category in loaded for category in memory._CATEGORIES))

    def test_corrupt_primary_recovers_last_valid_backup(self):
        memory.save_memory({"notes": {"first": {"value": "safe"}}})
        memory.save_memory({"notes": {"second": {"value": "new"}}})
        memory.MEMORY_PATH.write_text("{not valid json", encoding="utf-8")

        recovered = memory.load_memory()

        self.assertEqual(recovered["notes"]["first"]["value"], "safe")
        self.assertIsNotNone(json.loads(memory.MEMORY_PATH.read_text(encoding="utf-8")))

    def test_session_summary_survives_restart_style_reload_and_is_consumed_once(self):
        memory.save_session_summary("Finished the test task", "en")

        stored = memory.load_memory()
        self.assertEqual(stored["sessions"][-1]["summary"], "Finished the test task")
        self.assertEqual(memory.pop_last_session()["language"], "en")
        self.assertIsNone(memory.pop_last_session())

    def test_retrieval_is_bounded_relevant_and_keeps_unrelated_facts_out(self):
        memory.update_memory({
            "notes": {"garden": "User grows flowers in the garden"},
            "projects": {"release": "Prepare desktop release notes"},
        })

        facts = memory.retrieve_memory("garden flowers", limit=5)
        prompt = memory.format_memory_for_prompt(memory.load_memory(), "garden flowers")

        self.assertEqual([(fact["category"], fact["key"]) for fact in facts], [("notes", "garden")])
        self.assertIn("Garden: User grows flowers", prompt)
        self.assertNotIn("desktop release", prompt)


if __name__ == "__main__":
    unittest.main()
