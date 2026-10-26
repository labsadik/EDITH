"""Phase 4: lightweight task presentation and existing-UI regression contracts.

No cloud API, audio device, GUI instance or local model is required.
"""
import unittest
from pathlib import Path

from core.task_view import compact_task_view


ROOT = Path(__file__).resolve().parents[1]


class TaskViewTests(unittest.TestCase):
    def test_running_and_queued_are_prioritized_over_recent_history(self):
        states = [
            {"id": "1", "status": "succeeded", "label": "Older result"},
            {"id": "2", "status": "failed", "label": "Failed action"},
            {"id": "3", "status": "queued", "label": "Waiting action"},
            {"id": "4", "status": "running", "label": "Current action"},
        ]
        view = compact_task_view(states)
        self.assertEqual(
            [item["status"] for item in view["visible"]],
            ["running", "queued", "failed", "succeeded"],
        )
        self.assertEqual(view["running"], 1)
        self.assertEqual(view["queued"], 1)
        self.assertEqual(view["completed"], 1)
        self.assertEqual(view["failed"], 1)

    def test_only_display_metadata_is_exposed(self):
        states = [{"status": "running", "label": "Look up apps",
                   "args": {"api_key": "never_show_this", "text": "private"},
                   "result": "hidden_result", "error": "private_stacktrace"}]
        view = compact_task_view(states)
        self.assertEqual(
            view["visible"], [{"status": "running", "label": "Look up apps"}],
        )
        self.assertNotIn("never_show_this", str(view))
        self.assertNotIn("private_stacktrace", str(view))
        self.assertNotIn("hidden_result", str(view))

    def test_long_or_multiline_names_are_bounded_and_plain(self):
        task = compact_task_view([
            {"label": "alpha\n" + "b" * 200 + "\x00", "status": "queued"}
        ])["visible"][0]["label"]
        self.assertLessEqual(len(task), 76)
        self.assertNotIn("\n", task)
        self.assertNotIn("\x00", task)

    def test_rejects_invalid_limits_and_unrecognized_status(self):
        for limit in (0, 9, -1):
            with self.assertRaises(ValueError):
                compact_task_view([], limit=limit)
        self.assertEqual(compact_task_view([{"status": "unknown"}])["total"], 0)

    def test_active_tasks_keep_scheduler_order(self):
        states = [{"label": str(n), "status": "running"} for n in range(7)]
        view = compact_task_view(states)
        self.assertEqual(view["running"], 7)
        self.assertEqual([v["label"] for v in view["visible"]], ["0", "1", "2", "3"])

    def test_recent_results_are_newest_first(self):
        states = [{"label": str(n), "status": "succeeded"} for n in range(5)]
        view = compact_task_view(states)
        self.assertEqual(view["completed"], 5)
        self.assertEqual([v["label"] for v in view["visible"]], ["4", "3", "2", "1"])


class Phase4UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ui = (ROOT / "ui.py").read_text(encoding="utf-8")
        cls.main = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.llm = (ROOT / "core" / "llm_client.py").read_text(encoding="utf-8")

    def test_keeps_existing_hud_and_adds_details_in_place(self):
        self.assertIn("self.hud = HudCanvas(", self.ui)
        self.assertIn("self._center_split = QSplitter(", self.ui)
        self.assertIn("TASKS  0 RUN  ·  0 WAIT", self.ui)
        self.assertIn('lay.addWidget(_sec("ACTIVITY LOG"))', self.ui)
        self.assertIn("self._task_details_panel = QFrame()", self.ui)
        self.assertIn("self._task_details_panel.hide()", self.ui)
        self.assertIn("self._task_details_btn.toggled.connect(", self.ui)
        self.assertIn("self._task_details_btn.setEnabled(total > 0)", self.ui)

    def test_cross_thread_ui_updates_and_input_accessibility(self):
        self.assertIn("task_detail_signal = pyqtSignal(object)", self.ui)
        self.assertIn("self.task_detail_signal.connect(self._update_task_details)", self.ui)
        # Qt signals can outlive their QWidget during shutdown.  Task status
        # must use EdithUI's guarded emitter rather than dereferencing _win.
        self.assertIn('self.ui._emit_if_open("task_detail_signal", view)', self.main)
        self.assertIn('self.ui._emit_if_open(', self.main)
        self.assertNotIn("self.ui._win.task_detail_signal.emit(view)", self.main)
        self.assertIn("compact_task_view(states)", self.main)
        self.assertIn('QShortcut(QKeySequence("Ctrl+K"), self)', self.ui)
        self.assertIn('self._input.setAccessibleName("EDITH command input")', self.ui)

    def test_log_and_resize_optimizations_do_not_modify_model_config(self):
        self.assertIn("self.document().setMaximumBlockCount(700)", self.ui)
        self.assertIn("self._adjust_side_panels()", self.ui)
        self.assertIn("self._right_panel.width() - pw", self.ui)
        self.assertIn("def get_llm_provider()", self.llm)
        self.assertIn("def call_llm_text(", self.llm)
        self.assertIn("def call_llm_stream(", self.llm)
        self.assertIn(
            'LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"',
            self.main,
        )


if __name__ == "__main__":
    unittest.main()
