"""Local Project Manager persistence and bounded plan validation."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agents import project_manager


class ProjectManagerTests(unittest.TestCase):
    def test_plan_persists_bounded_tasks_and_status_updates(self):
        model = {
            "project_name": "Example Workspace",
            "summary": "Build a small test project.",
            "milestones": [
                {"title": "Foundation", "tasks": [
                    {"title": "Create project skeleton", "description": "Create folders."},
                    {"title": "Add tests", "description": "Add unit tests."},
                ]}
            ],
        }
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(project_manager, "STORE", Path(folder) / "projects.json"), \
             patch("core.brain_router.call_brain_text", return_value=json.dumps(model)):
            created = project_manager.plan_project("Build an example workspace", "example-workspace")
            self.assertEqual(created["version"], "1.0.0")
            self.assertEqual(len(created["tasks"]), 2)
            updated = project_manager.update_task("example-workspace", "T001", "completed")
            self.assertEqual(updated["task"]["status"], "completed")
            status = project_manager.format_project_status(project_manager.get_project("example-workspace"))
            self.assertIn("T001 [completed]", status)
            persisted = json.loads((Path(folder) / "projects.json").read_text(encoding="utf-8"))
            self.assertIn("example-workspace", persisted["projects"])

    def test_plan_rejects_invalid_model_structure_without_saving(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(project_manager, "STORE", Path(folder) / "projects.json"), \
             patch("core.brain_router.call_brain_text", return_value='{"milestones":[]}'):
            with self.assertRaises(RuntimeError):
                project_manager.plan_project("Bad plan", "bad-plan")
            self.assertFalse((Path(folder) / "projects.json").exists())

    def test_invalid_project_and_task_status_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            project_manager, "STORE", Path(folder) / "projects.json"
        ):
            with self.assertRaises(ValueError):
                project_manager.update_task("../outside", "T001", "completed")
            with self.assertRaises(ValueError):
                project_manager.update_task("demo", "T001", "running")

    def test_unavailable_ollama_returns_actionable_error_and_does_not_save(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(project_manager, "STORE", Path(folder) / "projects.json"), \
             patch("core.brain_router.call_brain_text", side_effect=RuntimeError(
                 "Cannot connect to Ollama at http://localhost:11434. Make sure Ollama is installed."
             )):
            result = project_manager.run_project_manager(
                "plan", "edith-agent-test", "Build a Hello World app"
            )
            self.assertIn("Project plan was NOT saved", result)
            self.assertIn("POWERFUL BRAIN", result)
            self.assertIn("ollama serve", result.lower())
            self.assertFalse((Path(folder) / "projects.json").exists())

    def test_status_for_project_whose_plan_failed_is_user_friendly(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            project_manager, "STORE", Path(folder) / "projects.json"
        ):
            result = project_manager.run_project_manager("status", "edith-agent-test")
            self.assertIn("No saved project named 'edith-agent-test'", result)
            self.assertIn("action=plan", result)
            self.assertNotIn("Traceback", result)


if __name__ == "__main__":
    unittest.main()
