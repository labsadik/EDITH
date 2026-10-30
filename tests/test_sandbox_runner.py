"""Fail-closed contract tests for the local Rust sandbox bridge."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from core import sandbox_runner


class SandboxRunnerTests(unittest.TestCase):
    def test_runner_passes_workspace_timeout_network_and_exact_argv(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            binary = Path(folder) / "edith-sandbox"
            binary.write_text("test stub", encoding="utf-8")
            completed = subprocess.CompletedProcess(["sandbox"], 0, "ok", "")
            with (
                patch.object(sandbox_runner, "ensure_sandbox_ready", return_value=binary),
                patch.object(sandbox_runner.subprocess, "run", return_value=completed) as run,
            ):
                receipt = sandbox_runner.run_sandboxed(
                    ["python", "main.py"], workspace=workspace, timeout=17, network=False
                )
            self.assertEqual(receipt.stdout, "ok")
            command = run.call_args.args[0]
            self.assertIn("--workspace", command)
            self.assertIn(str(workspace), command)
            self.assertIn("--timeout", command)
            self.assertIn("17", command)
            self.assertIn("--network", command)
            self.assertIn("deny", command)
            self.assertIn("--memory-mb", command)
            self.assertIn("2048", command)
            self.assertIn("--cpu-seconds", command)
            self.assertEqual(command[-2:], ["python", "main.py"])

    def test_runner_forwards_only_explicit_stdin(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / "edith-sandbox"
            binary.write_text("test stub", encoding="utf-8")
            with (
                patch.object(sandbox_runner, "ensure_sandbox_ready", return_value=binary),
                patch.object(
                    sandbox_runner.subprocess, "run",
                    return_value=subprocess.CompletedProcess(["sandbox"], 0, "", ""),
                ) as run,
            ):
                sandbox_runner.run_sandboxed(
                    ["python", "worker.py"], workspace=folder,
                    input_data='{"source":"print(1)"}',
                )
            self.assertEqual(run.call_args.kwargs["input"], '{"source":"print(1)"}')

    def test_missing_rust_sandbox_never_falls_back_to_host_shell(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            with patch.object(
                sandbox_runner, "ensure_sandbox_ready",
                side_effect=sandbox_runner.SandboxUnavailable("sandbox unavailable"),
            ), patch.object(sandbox_runner.subprocess, "run") as run:
                result = sandbox_runner.run_project_command(
                    "python main.py", workspace=workspace, timeout=10
                )
            run.assert_not_called()
            self.assertIn("host execution was not attempted", result)
            self.assertIn("sandbox unavailable", result)

    def test_project_venv_is_created_inside_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            python = sandbox_runner.ensure_project_venv(folder)
            self.assertTrue(python.is_file())
            self.assertTrue(python.is_relative_to(Path(folder).resolve()))

    @unittest.skipIf(os.name == "nt", "symlink creation may require elevated Windows developer mode")
    def test_symlinked_workspace_is_rejected_before_sandbox_creation(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            link = Path(folder) / "linked-workspace"
            link.symlink_to(Path(outside), target_is_directory=True)
            with patch.object(sandbox_runner, "ensure_sandbox_ready") as build:
                with self.assertRaises(ValueError):
                    sandbox_runner.run_sandboxed(["python", "main.py"], workspace=link)
            build.assert_not_called()

    @unittest.skipIf(os.name == "nt", "symlink creation may require elevated Windows developer mode")
    def test_external_project_venv_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            workspace = Path(folder)
            (workspace / ".venv").symlink_to(Path(outside), target_is_directory=True)
            with self.assertRaises(sandbox_runner.SandboxUnavailable):
                sandbox_runner.ensure_project_venv(workspace)


if __name__ == "__main__":
    unittest.main()
