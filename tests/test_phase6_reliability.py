"""Phase 6 regression tests: no-replay, truthful verification and private history."""
import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.agent_reliability import (
    ActionDeduplicator, AgentTaskJournal, assess_action_evidence,
    format_task_history,
)
from core.task_scheduler import TaskReportedFailure, TaskScheduler, TaskSpec, parallel_read_only

ROOT = Path(__file__).resolve().parents[1]


class ActionEvidenceTests(unittest.TestCase):
    def test_successful_side_effect_is_reported_not_independently_verified(self):
        result = assess_action_evidence("file_controller", {"action": "create_folder"}, "Folder created successfully.")
        self.assertEqual(result.status, "reported")
        self.assertEqual(result.verification, "follow_up_required")
        self.assertFalse(result.blocks_dependents)
        self.assertIn("read-only observation", result.response_metadata()["guidance"])

    def test_read_only_result_does_not_require_effect_verification(self):
        for name, args in [
            ("web_search", {"mode": "search"}),
            ("file_controller", {"action": "list"}),
            ("task_history", {}),
        ]:
            with self.subTest(name=name):
                evidence = assess_action_evidence(name, args, "Found 3 results.")
                self.assertEqual(evidence.verification, "tool_reported")
                self.assertFalse(evidence.blocks_dependents)
        self.assertTrue(parallel_read_only("task_history"))

    def test_unverified_and_missing_receipt_never_unblock_dependents(self):
        for message in (
            "Done.", "", "Launch request submitted; could not verify that it opened.",
            "Delivery is unverified; no delivery receipt.",
            "Permission denied", "No results", "Cancelled by user; no action was executed.",
        ):
            with self.subTest(message=message):
                outcome = assess_action_evidence("open_app", {"action": "open"}, message)
                self.assertTrue(outcome.blocks_dependents)
                self.assertIn(outcome.status, {"failed", "cancelled", "unverified"})

    def test_cancellation_status_is_distinct(self):
        evidence = assess_action_evidence(
            "send_message", {}, "Cancelled by user; no action was executed."
        )
        self.assertEqual(evidence.status, "cancelled")
        self.assertEqual(evidence.verification, "not_verified")

    def test_no_tool_args_in_model_metadata(self):
        token = "private-secret-message-never-log"
        result = assess_action_evidence("send_message", {"message_text": token}, "Sent successfully")
        self.assertNotIn(token, str(result.response_metadata()))


class DeduplicationTests(unittest.TestCase):
    def test_duplicate_and_conflict_do_not_claim_new_execution(self):
        dedup = ActionDeduplicator(limit=2)
        self.assertEqual(dedup.reserve("call-1", "send_message", {"text": "hello"}), "new")
        self.assertEqual(dedup.reserve("call-1", "send_message", {"text": "hello"}), "duplicate")
        self.assertEqual(dedup.reserve("call-1", "send_message", {"text": "changed"}), "conflict")
        self.assertEqual(dedup.reserve("", "send_message", {}), "untracked")

    def test_bounded_memory_contains_digest_not_original_arguments(self):
        dedup = ActionDeduplicator(limit=2)
        secret = "super-private-outbound-message"
        dedup.reserve("one", "send_message", {"message_text": secret})
        self.assertEqual(len(dedup._seen["one"]), 32)
        self.assertNotIn(secret, repr(dedup._seen))
        dedup.reserve("two", "open_app", {"app_name": "Calculator"})
        dedup.reserve("three", "send_message", {"message_text": "test"})
        self.assertNotIn("one", dedup._seen)
        self.assertEqual(len(dedup._seen), 2)


class JournalTests(unittest.TestCase):
    def test_interrupted_work_is_marked_not_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "history.sqlite3"
            journal = AgentTaskJournal(db)
            self.assertTrue(journal.available)
            self.assertTrue(journal.plan([
                ("run1-1", "file_controller"),
                ("run1-2", "send_message"),
            ]))
            self.assertTrue(journal.started("run1-1"))
            recovered = AgentTaskJournal(db)
            rows = recovered.recent()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["status"] == "interrupted" for row in rows))
            self.assertTrue(all(row["verification"] == "not_verified" for row in rows))
            self.assertFalse(any(row["status"] == "succeeded" for row in rows))

    def test_only_metadata_is_persisted_with_bounded_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "audit.sqlite3"
            journal = AgentTaskJournal(path, retention=10)
            secret = "do-not-store-my-api-key-or-message"
            for i in range(15):
                task_id = f"t-{i}"
                journal.plan([(task_id, "file_controller")])
                journal.started(task_id)
                journal.finished(task_id, "succeeded", "follow_up_required", 11)
            recent = journal.recent(limit=30)
            self.assertEqual(len(recent), 10)
            self.assertNotIn(secret, repr(recent))
            with closing(sqlite3.connect(path)) as db:
                raw = "\n".join(str(row) for row in db.execute("SELECT * FROM tasks"))
            self.assertNotIn("message_text", raw)
            self.assertNotIn("path", raw)
            self.assertNotIn(secret, raw)
            self.assertNotIn("t-0", raw)
            self.assertIn("t-14", raw)

    def test_pending_tasks_are_not_lost_during_history_pruning(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = AgentTaskJournal(Path(temp) / "history.sqlite3", retention=10)
            journal.plan([(f"run-{i}", "web_search") for i in range(16)])
            for i in range(11):
                journal.finished(f"run-{i}", "succeeded", "tool_reported", 5)
            with closing(sqlite3.connect(journal.path)) as db:
                waiting = db.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'").fetchone()[0]
                complete = db.execute("SELECT COUNT(*) FROM tasks WHERE status='succeeded'").fetchone()[0]
            self.assertEqual(waiting, 5)
            self.assertEqual(complete, 10)

    def test_unavailable_storage_does_not_break_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            file_path = Path(temp) / "not-a-folder"
            file_path.write_text("occupied", encoding="utf-8")
            journal = AgentTaskJournal(file_path / "history.sqlite3")
            self.assertFalse(journal.available)
            self.assertFalse(journal.plan([("x", "web_search")]))
            self.assertEqual(journal.recent(), [])

    def test_summary_contains_no_arguments_or_results(self):
        summary = format_task_history([
            {"tool": "file_controller", "status": "interrupted",
             "verification": "not_verified", "secret_message": "never-display"},
        ])
        self.assertIn("file_controller: interrupted", summary)
        self.assertNotIn("never-display", summary)


class IntegrationContractTests(unittest.TestCase):
    def test_main_wires_dedup_evidence_and_history_without_changing_models(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("ActionDeduplicator()", main)
        self.assertIn("AgentTaskJournal()", main)
        self.assertIn("assess_action_evidence(", main)
        self.assertIn("execution_verification", main)
        self.assertIn('"name": "task_history"', main)
        self.assertIn('LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"', main)
        llm = (ROOT / "core" / "llm_client.py").read_text(encoding="utf-8")
        for item in ("llm_provider", "llm_url", "llm_model"):
            self.assertIn(item, llm)


class DependencyRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_dangerous_action_not_retried_and_blocks_dependents(self):
        scheduler = TaskScheduler(max_concurrency=4)
        called = []
        original = {"result": "Cancelled by user; no action was executed."}

        async def cancelled():
            called.append("first")
            raise TaskReportedFailure(original, status="cancelled")

        async def dependent():
            called.append("danger")
            return "should-not-run"

        outcomes = await scheduler.run_batch([
            TaskSpec("a", "Send message", cancelled, exclusive=True, retry_limit=5),
            TaskSpec("b", "More changes", dependent, exclusive=True, depends_on=("a",)),
        ])
        self.assertEqual([item.status for item in outcomes], ["cancelled", "blocked"])
        self.assertEqual(called, ["first"])


if __name__ == "__main__":
    unittest.main()
