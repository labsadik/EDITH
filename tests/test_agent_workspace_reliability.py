from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from actions import code_helper, dev_agent


class CodeHelperWorkspaceTests(unittest.TestCase):
    def test_relative_outputs_use_the_shared_projects_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "EDITH Projects"
            with patch("core.branding.prepare_projects_dir", return_value=workspace):
                result = code_helper._resolve_save_path("Task_01/verify_environment.py", "python")
            self.assertEqual(
                result,
                workspace.resolve() / "Task_01" / "verify_environment.py",
            )

    def test_default_output_uses_the_same_workspace_as_dev_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "EDITH Projects"
            with patch("core.branding.prepare_projects_dir", return_value=workspace):
                self.assertEqual(
                    code_helper._resolve_save_path("", "python"),
                    workspace.resolve() / "edith_code.py",
                )

    def test_relative_output_cannot_escape_the_shared_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "EDITH Projects"
            with patch("core.branding.prepare_projects_dir", return_value=workspace):
                with self.assertRaises(ValueError):
                    code_helper._resolve_save_path("../outside.py", "python")

    def test_write_does_not_return_a_path_when_save_fails(self):
        class Response:
            text = "print('hello')"

        class Model:
            def generate_content(self, _prompt):
                return Response()

        with (
            patch.object(code_helper, "_get_gemini", return_value=Model()),
            patch.object(code_helper, "_resolve_save_path", return_value=Path("generated.py")),
            patch.object(code_helper, "_save_file", return_value="Could not save: permission denied"),
        ):
            with self.assertRaisesRegex(OSError, "permission denied"):
                code_helper._write("write a hello script", "python", "")


class DevelopmentAgentReliabilityTests(unittest.TestCase):
    def test_partial_project_generation_stops_before_dependencies_and_execution(self):
        plan = {
            "project_name": "partial_demo",
            "entry_point": "main.py",
            "files": [
                {"path": "helper.py", "description": "helper", "imports": []},
                {"path": "main.py", "description": "entry point", "imports": ["helper"]},
            ],
            "dependencies": ["example-package"],
            "run_command": "python main.py",
        }

        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "EDITH Projects"

            def write_one_file(*, file_info, project_dir, **_kwargs):
                relative_path = file_info["path"]
                if relative_path == "main.py":
                    raise dev_agent.RateLimitError("provider rate limited")
                target = dev_agent._safe_project_path(project_dir, relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("VALUE = 1\n", encoding="utf-8")
                return "VALUE = 1\n"

            with (
                patch.object(dev_agent, "_plan_project", return_value=plan),
                patch("actions.dev_agent.prepare_projects_dir", return_value=projects),
                patch("core.sandbox_runner.ensure_project_venv", return_value=Path(sys.executable)),
                patch("core.sandbox_runner.ensure_sandbox_ready"),
                patch.object(dev_agent, "_write_file", side_effect=write_one_file),
                patch.object(dev_agent.time, "sleep"),
                patch.object(dev_agent, "_install_dependencies") as install,
                patch.object(dev_agent, "_run_project") as run_project,
                patch.object(dev_agent, "_open_vscode") as open_vscode,
            ):
                result = dev_agent._build_project("demo", "python", "", 15)

            self.assertIn("Project generation incomplete", result)
            self.assertIn("main.py", result)
            install.assert_not_called()
            run_project.assert_not_called()
            open_vscode.assert_not_called()

    def test_normal_appcontainer_debug_trace_is_not_misclassified_as_infrastructure_failure(self):
        output = (
            "Execution failed (exit 1).\\n[stderr]\\n"
            "EDITH_SANDBOX_DEBUG create AppContainer profile elapsed_ms=1\\n"
            "Traceback (most recent call last): ValueError: bad project input"
        )
        self.assertFalse(dev_agent._is_sandbox_environment_failure(output))

    def test_sandbox_infrastructure_failure_is_not_sent_to_code_repair(self):
        plan = {
            "project_name": "sandbox_demo",
            "entry_point": "main.py",
            "files": [
                {"path": "main.py", "description": "entry point", "imports": []},
            ],
            "dependencies": [],
            "run_command": "python main.py",
        }

        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "EDITH Projects"

            def write_one_file(*, file_info, project_dir, **_kwargs):
                target = dev_agent._safe_project_path(project_dir, file_info["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("print('hello')\n", encoding="utf-8")
                return "print('hello')\n"

            security_report = {"counts": {"critical": 0}}
            sandbox_error = (
                "Execution failed (exit 2).\n[stderr]\n"
                "EDITH_SANDBOX_ERROR: Cannot apply sandbox ACL"
            )
            with (
                patch.object(dev_agent, "_plan_project", return_value=plan),
                patch("actions.dev_agent.prepare_projects_dir", return_value=projects),
                patch("core.sandbox_runner.ensure_project_venv", return_value=Path(sys.executable)),
                patch("core.sandbox_runner.ensure_sandbox_ready"),
                patch.object(dev_agent, "_write_file", side_effect=write_one_file),
                patch.object(dev_agent, "_open_vscode", return_value=False),
                patch("agents.devsecops.scan_project", return_value=security_report),
                patch("agents.devsecops.format_report", return_value="No findings"),
                patch.object(dev_agent, "_run_project", return_value=sandbox_error) as run_project,
                patch.object(dev_agent, "_fix_files") as fix_files,
            ):
                result = dev_agent._build_project("demo", "python", "", 15)

            self.assertIn("Sandbox execution failed", result)
            run_project.assert_called_once()
            fix_files.assert_not_called()


if __name__ == "__main__":
    unittest.main()
