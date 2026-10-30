"""Step 7 integration contracts for the shared, confirmed execution layer."""
import asyncio
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from actions.code_helper import _run_file
from actions.desktop import _execute_generated_code
from actions.dev_agent import _install_dependencies, _try_auto_install
from core.execution import ExecutionService, format_execution
from edith.platform.audit import AuditLog


class ExecutionServiceTests(unittest.TestCase):
    def service(self, approve=True, output=None):
        return ExecutionService(
            confirmer=(lambda *_: approve), output=output,
            audit=Mock(),
        )

    def test_decline_never_spawns_and_is_not_success(self):
        service = self.service(False)
        with patch("core.execution.run_streamed") as run:
            receipt = service.run_argv([sys.executable, "-c", "print('must not run')"])
        run.assert_not_called()
        self.assertFalse(receipt["ok"])
        self.assertIn("cancelled", format_execution(receipt).lower())

    def test_streamed_output_is_forwarded_and_success_has_exit_receipt(self):
        seen = []
        service = self.service(True, lambda line: seen.append(line))
        receipt = service.run_argv(
            [sys.executable, "-u", "-c", "print('hello', flush=True)"], timeout=3
        )
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["data"]["exit_code"], 0)
        self.assertIn("hello", receipt["data"]["stdout"])
        self.assertTrue(any("SHELL stdout:" in text and "hello" in text for text in seen))

    def test_timeout_is_not_reported_as_success(self):
        service = self.service(True)
        receipt = service.run_argv(
            [sys.executable, "-c", "import time; time.sleep(5)"], timeout=.12
        )
        self.assertFalse(receipt["ok"])
        self.assertTrue(receipt["data"]["timed_out"])
        self.assertIn("timed out", format_execution(receipt).lower())

    def test_interrupt_cancels_owned_process_and_future_job_command(self):
        service = self.service(True)
        started = threading.Event()
        result = []

        def worker():
            with service.job("integration"):
                started.set()
                result.append(service.run_argv(
                    [sys.executable, "-c", "import time; time.sleep(5)"], timeout=10
                ))

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(started.wait(1))
        time.sleep(.12)
        service.cancel()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result and result[0]["data"]["cancelled"])

        # A new task can run after an interrupt; an already-running context
        # retains the old generation and cannot start another command.
        with service.job("integration"):
            service.cancel()
            denied = service.run_argv([sys.executable, "-c", "print('stale')"])
        self.assertFalse(denied["ok"])
        self.assertIn("cancelled", format_execution(denied).lower())

    def test_source_is_reviewed_by_hash_and_mutation_after_approval_is_denied(self):
        service = self.service(True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "task.py"
            path.write_text("print('before')", encoding="utf-8")
            original = service.broker.confirmer

            def approve_then_mutate(title, preview):
                path.write_text("print('changed')", encoding="utf-8")
                return original(title, preview)

            service.broker.confirmer = approve_then_mutate
            with patch("core.execution.run_streamed") as run:
                receipt = service.run_argv([sys.executable, str(path)], source_path=path)
            run.assert_not_called()
        self.assertFalse(receipt["ok"])
        self.assertIn("cancelled", format_execution(receipt).lower())


class LegacyToolIntegrationTests(unittest.TestCase):
    def test_code_helper_preserves_quoted_arguments_and_uses_actual_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "echo args.py"
            path.write_text("import sys; print('|'.join(sys.argv[1:]))", encoding="utf-8")
            def fake_sandbox(argv, *, workspace, timeout=30, **kwargs):
                return subprocess.run(
                    [str(item) for item in argv], cwd=str(workspace),
                    capture_output=True, text=True, timeout=timeout, check=False,
                )
            with patch("core.sandbox_runner.run_sandboxed", side_effect=fake_sandbox) as sandbox:
                result = _run_file(path, '"two words" plain', 3)
        self.assertIn("two words|plain", result)
        self.assertEqual(sandbox.call_count, 1)
        self.assertFalse(sandbox.call_args.kwargs["network"])

    def test_desktop_generated_code_fails_closed_without_rust_sandbox(self):
        from core.sandbox_runner import SandboxUnavailable
        with patch(
            "core.sandbox_runner.run_sandboxed",
            side_effect=SandboxUnavailable("sandbox unavailable"),
        ) as sandbox:
            result = _execute_generated_code("print('ok')")
        self.assertIn("sandbox unavailable", result.lower())
        self.assertIn("not run on the host", result.lower())
        sandbox.assert_called_once()


    def test_dependency_install_uses_rust_sandbox_and_scoped_network(self):
        with tempfile.TemporaryDirectory() as folder:
            python = Path(folder) / "python.exe"
            failed = subprocess.CompletedProcess([], 1, "", "package install failed")
            with patch("core.sandbox_runner.run_sandboxed", return_value=failed) as sandbox:
                result = _install_dependencies(["requests==2.32.3"], Path.cwd(), python)
                self.assertIn("Execution failed", result)
                command = sandbox.call_args.args[0]
                self.assertEqual(command[:4], [str(python), "-m", "pip", "install"])
                self.assertIn("requests==2.32.3", command)
                self.assertTrue(sandbox.call_args.kwargs["network"])
                self.assertEqual(sandbox.call_args.kwargs["workspace"], Path.cwd())

                self.assertFalse(_try_auto_install(
                    "ModuleNotFoundError: No module named 'requests'", Path.cwd(), python
                ))
                self.assertEqual(sandbox.call_count, 2)


class DispatchContractTests(unittest.TestCase):
    def test_shell_tool_is_declared_with_progress_and_timeout(self):
        source = Path(__file__).resolve().parents[1] / "main.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn('"name":"shell_execute"', text)
        self.assertIn("Report the intended command before running it", text)
        self.assertIn("await run_code_tool(EXECUTION.shell", text)


if __name__ == "__main__":
    unittest.main()

