"""Phase 3 scheduler behavior: concurrency, ordering, failures and cancellation."""

import asyncio
import unittest

from core.action_activity import activity_outcome

from core.task_scheduler import (
    TaskReportedFailure, TaskScheduler, TaskSpec, parallel_read_only,
)


class TaskSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_independent_actions_run_together_and_return_in_order(self):
        scheduler = TaskScheduler(max_concurrency=4)
        release = asyncio.Event()
        all_started = asyncio.Event()
        active = 0
        maximum = 0

        async def work(n):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            if active == 4:
                all_started.set()
            await release.wait()
            active -= 1
            return n

        specs = [
            TaskSpec(f"read-{n}", f"Read {n}", lambda n=n: work(n))
            for n in range(4)
        ]
        batch = asyncio.create_task(scheduler.run_batch(specs))
        await asyncio.wait_for(all_started.wait(), timeout=2)
        self.assertEqual(maximum, 4)
        self.assertEqual(sum(s["status"] == "running" for s in scheduler.snapshot()), 4)
        release.set()
        results = await asyncio.wait_for(batch, timeout=2)
        self.assertEqual([result.value for result in results], [0, 1, 2, 3])
        self.assertTrue(all(result.status == "succeeded" for result in results))

    async def test_scheduler_limits_concurrency(self):
        scheduler = TaskScheduler(max_concurrency=2)
        active = 0
        peak = 0

        async def work():
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return "ok"

        results = await scheduler.run_batch([
            TaskSpec(str(n), "Read", work) for n in range(7)
        ])
        self.assertEqual(peak, 2)
        self.assertTrue(all(r.status == "succeeded" for r in results))

    async def test_barrier_waits_for_reads_and_subsequent_actions(self):
        scheduler = TaskScheduler()
        traces = []
        async def read(n):
            traces.append(f"start {n}")
            await asyncio.sleep(0.01)
            traces.append(f"end {n}")
            return n

        async def change():
            traces.append("change")
            return "changed"

        tasks = [
            TaskSpec("a", "Read A", lambda: read("a")),
            TaskSpec("b", "Read B", lambda: read("b")),
            TaskSpec("c", "Change", change, depends_on=("a", "b"), exclusive=True),
            TaskSpec("d", "Read D", lambda: read("d"), depends_on=("c",)),
        ]
        result = await scheduler.run_batch(tasks)
        self.assertTrue(all(item.status == "succeeded" for item in result))
        self.assertLess(traces.index("end a"), traces.index("change"))
        self.assertLess(traces.index("end b"), traces.index("change"))
        self.assertLess(traces.index("change"), traces.index("start d"))

    async def test_priority_selects_higher_priority_first(self):
        scheduler = TaskScheduler(max_concurrency=1)
        order = []
        async def work(name):
            order.append(name)
            return name

        result = await scheduler.run_batch([
            TaskSpec("low", "Low", lambda: work("low"), priority=20),
            TaskSpec("high", "High", lambda: work("high"), priority=0),
            TaskSpec("medium", "Medium", lambda: work("medium"), priority=10),
        ])
        self.assertEqual(order, ["high", "medium", "low"])
        self.assertEqual([r.value for r in result], ["low", "high", "medium"])

    async def test_cancel_only_queued_tasks(self):
        scheduler = TaskScheduler(max_concurrency=1)
        started = asyncio.Event()
        release = asyncio.Event()
        called = []

        async def first():
            started.set()
            await release.wait()
            return "first"

        async def second():
            called.append("second")
            return "second"

        batch = asyncio.create_task(scheduler.run_batch([
            TaskSpec("one", "One", first),
            TaskSpec("two", "Two", second),
        ]))
        await asyncio.wait_for(started.wait(), timeout=2)
        self.assertEqual(scheduler.cancel_queued("one"), 0)
        self.assertEqual(scheduler.cancel_queued("two"), 1)
        release.set()
        results = await asyncio.wait_for(batch, timeout=2)
        self.assertEqual([r.status for r in results], ["succeeded", "cancelled"])
        self.assertEqual(called, [])

    async def test_global_cancel_interrupts_running_wrapper_and_never_reports_success(self):
        scheduler = TaskScheduler(max_concurrency=2)
        started = asyncio.Event()
        release = asyncio.Event()
        completed = []

        async def running():
            started.set()
            try:
                await release.wait()
            finally:
                completed.append("finally")
            return "must-not-be-used"

        batch = asyncio.create_task(scheduler.run_batch([
            TaskSpec("active", "Active operation", running, exclusive=True),
        ]))
        await asyncio.wait_for(started.wait(), timeout=2)
        stats = scheduler.cancel_all()
        self.assertEqual(stats["running"], 1)
        results = await asyncio.wait_for(batch, timeout=2)
        self.assertEqual(results[0].status, "interrupted")
        self.assertIsNone(results[0].value)
        self.assertEqual(completed, ["finally"])

    async def test_global_cancel_marks_queued_dependents_without_starting_them(self):
        scheduler = TaskScheduler(max_concurrency=1)
        started = asyncio.Event()
        release = asyncio.Event()
        called = []

        async def first():
            started.set()
            await release.wait()

        async def queued():
            called.append(True)

        batch = asyncio.create_task(scheduler.run_batch([
            TaskSpec("first", "First", first),
            TaskSpec("queued", "Queued", queued),
        ]))
        await asyncio.wait_for(started.wait(), timeout=2)
        stats = scheduler.cancel_all()
        self.assertEqual(stats["queued"], 1)
        release.set()
        results = await asyncio.wait_for(batch, timeout=2)
        self.assertEqual([r.status for r in results], ["interrupted", "cancelled"])
        self.assertEqual(called, [])

    async def test_failure_blocks_dependent_actions(self):
        scheduler = TaskScheduler()
        called = []
        async def fail():
            raise ValueError("read failed")

        async def dependent():
            called.append("unsafe")
            return True

        results = await scheduler.run_batch([
            TaskSpec("a", "Fail", fail),
            TaskSpec("b", "Unsafe", dependent, depends_on=("a",), exclusive=True),
        ])
        self.assertEqual([r.status for r in results], ["failed", "blocked"])
        self.assertEqual(called, [])

    async def test_user_cancellation_preserves_exact_tool_result_and_blocks(self):
        scheduler = TaskScheduler()
        original = {"result": "Cancelled by user; no action was executed."}
        called = []

        async def cancelled_action():
            raise TaskReportedFailure(original, status="cancelled")

        async def dependent():
            called.append("should not run")

        results = await scheduler.run_batch([
            TaskSpec("a", "Confirm", cancelled_action, exclusive=True),
            TaskSpec("b", "Next", dependent, depends_on=("a",), exclusive=True),
        ])
        self.assertEqual(results[0].status, "cancelled")
        self.assertIs(results[0].value, original)
        self.assertEqual(results[1].status, "blocked")
        self.assertEqual(called, [])

    async def test_retry_is_opt_in_for_safe_operations_only(self):
        scheduler = TaskScheduler()
        attempts = {"unsafe": 0, "safe": 0}

        async def unsafe():
            attempts["unsafe"] += 1
            raise RuntimeError("transient")

        async def safe():
            attempts["safe"] += 1
            if attempts["safe"] == 1:
                raise RuntimeError("temporary")
            return "recovered"

        results = await scheduler.run_batch([
            TaskSpec("a", "Unsafe", unsafe, retry_limit=3, retry_safe=False),
            TaskSpec("b", "Safe", safe, retry_limit=1, retry_safe=True),
        ])
        self.assertEqual(results[0].status, "failed")
        self.assertEqual(results[1].status, "succeeded")
        self.assertEqual(attempts, {"unsafe": 1, "safe": 2})

    async def test_invalid_dependency_never_executes(self):
        scheduler = TaskScheduler()
        called = []
        async def perform():
            called.append(True)
        result = await scheduler.run_batch([
            TaskSpec("a", "Unknown dependency", perform, depends_on=("missing",))
        ])
        self.assertEqual(result[0].status, "blocked")
        self.assertFalse(called)

    def test_failed_file_reads_and_cancellations_are_not_success(self):
        for result in (
            "Access denied: protected-file.txt",
            "Path not found: missing-folder",
            "File not found: missing.txt",
            "Not a directory: example",
            "Cancelled by user; no action was executed.",
        ):
            with self.subTest(result=result):
                self.assertEqual(activity_outcome(result), "error")

    def test_classifier_is_allowlist_only(self):
        self.assertTrue(parallel_read_only("web_search", {"mode": "research"}))
        self.assertTrue(parallel_read_only("system_status"))
        self.assertTrue(parallel_read_only("file_controller", {"action": "read"}))
        self.assertTrue(parallel_read_only("file_controller", {"action": "find"}))
        self.assertTrue(parallel_read_only("open_app", {"action": "search"}))
        self.assertTrue(parallel_read_only("manage_monitor", {"action": "list"}))
        for name, args in [
            ("computer_control", {"action": "click"}),
            ("browser_control", {"action": "navigate"}),
            ("file_controller", {"action": "delete"}),
            ("file_controller", {"action": "create_folders"}),
            ("file_controller", {"action": "write"}),
            ("computer_settings", {"action": "shutdown"}),
            ("send_message", {"receiver": "someone"}),
            ("dev_agent", {}),
            ("weather_report", {}),
            ("unknown_plugin_tool", {}),
            ("open_app", {"action": "open"}),
            ("manage_monitor", {"action": "add"}),
        ]:
            with self.subTest(tool=name, args=args):
                self.assertFalse(parallel_read_only(name, args))


if __name__ == "__main__":
    unittest.main()

