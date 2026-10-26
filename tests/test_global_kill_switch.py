"""Global interrupt wiring contracts (no live device or Qt window required)."""
from pathlib import Path
import unittest


class GlobalKillSwitchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")

    def test_interrupt_invalidates_generation_and_stops_all_owned_paths(self):
        self.assertIn("self._kill_switch_generation += 1", self.main)
        self.assertIn("EXECUTION.cancel()", self.main)
        self.assertIn("loop.call_soon_threadsafe(self._cancel_global_tasks)", self.main)
        self.assertIn("self._task_scheduler.cancel_all()", self.main)
        self.assertIn("queue.get_nowait()", self.main)
        self.assertIn("self.audio_in_queue.clear()", self.main)

    def test_scheduler_reports_interrupted_results_instead_of_success(self):
        source = (Path(__file__).resolve().parents[1] / "core" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn("def cancel_all(self)", source)
        self.assertIn('"Interrupted by the global kill switch"', source)
        self.assertIn('key, "interrupted"', source)


if __name__ == "__main__":
    unittest.main()
