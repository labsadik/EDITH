"""Bounded, observable task scheduling for EDITH.

Live tool calls are allowed to overlap only when each action is explicitly
classified as an independent read-only lookup. Actions affecting the desktop,
files, messages or model session remain ordered and require their existing
confirmation checks. Cancellation never pretends to stop a running OS action.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping


_TERMINAL = {"succeeded", "failed", "blocked", "cancelled", "interrupted"}

# Deliberate allowlist: new and unknown tools remain sequential by default.
_READ_ONLY_TOOLS = {"web_search", "system_status", "performance_metrics", "task_history"}
_READ_ONLY_FILE_ACTIONS = {"list", "read", "find", "info", "largest", "disk_usage"}
_READ_ONLY_OPEN_APP_ACTIONS = {"list", "list_installed", "discover", "search", "find"}


def parallel_read_only(name: str, arguments: Mapping[str, Any] | None = None) -> bool:
    """Only verified non-mutating tool variants may execute concurrently."""
    args = arguments or {}
    action = str(args.get("action") or "").strip().lower()
    if name in _READ_ONLY_TOOLS:
        return True
    if name == "project_manager":
        return action in {"status", "list"}
    if name == "file_controller":
        return action in _READ_ONLY_FILE_ACTIONS
    if name == "open_app":
        return action in _READ_ONLY_OPEN_APP_ACTIONS
    if name == "manage_monitor":
        return action == "list"
    return False


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    label: str
    run: Callable[[], Awaitable[Any]]
    priority: int = 10                  # Lower values run first.
    depends_on: tuple[str, ...] = ()
    exclusive: bool = False
    retry_limit: int = 0
    retry_safe: bool = False            # Never retry side effects implicitly.


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    status: str
    value: Any = None
    error: str = ""
    attempts: int = 0


class TaskReportedFailure(Exception):
    """A tool returned an unsuccessful result that should block dependents."""

    def __init__(self, response: Any, status: str = "failed"):
        if status not in {"failed", "cancelled"}:
            raise ValueError("Reported failure status must be failed or cancelled")
        super().__init__("Tool reported an unsuccessful or cancelled operation")
        self.response = response
        self.status = status


class TaskScheduler:
    """Run task batches with dependency, priority and cancellation tracking.

    The caller awaits all results in input order. Only waiting tasks can be
    cancelled; already-running operations are NOT interrupted. This matters
    for OS tools that execute in threads and cannot be safely killed.
    """

    def __init__(
        self,
        max_concurrency: int = 4,
        on_update: Callable[[list[dict]], None] | None = None,
    ):
        if not 1 <= max_concurrency <= 4:
            raise ValueError("Concurrency must be between 1 and 4")
        self.max_concurrency = max_concurrency
        self.on_update = on_update
        self._states: dict[str, dict] = {}
        self._exclusive_lock = asyncio.Lock()
        self._running_tasks: dict[asyncio.Task, str] = {}
        self._cancelled_running: set[str] = set()

    def snapshot(self) -> list[dict]:
        """Return metadata only, never tool parameters, results or secrets."""
        return [dict(state) for state in self._states.values()]

    def _notify(self) -> None:
        if self.on_update:
            try:
                self.on_update(self.snapshot())
            except Exception:
                # A UI listener must never stop task execution.
                pass

    def _update(self, task_id: str, status: str, attempts: int | None = None) -> None:
        state = self._states[task_id]
        state["status"] = status
        if attempts is not None:
            state["attempts"] = attempts
        self._notify()

    def cancel_queued(self, task_id: str | None = None) -> int:
        """Cancel one or all QUEUED tasks; running actions are untouched."""
        cancelled = 0
        for key, state in self._states.items():
            if (task_id is None or key == task_id) and state["status"] == "queued":
                state["status"] = "cancelled"
                cancelled += 1
        if cancelled:
            self._notify()
        return cancelled

    def cancel_all(self) -> dict[str, int]:
        """Cancel queued work and interrupt scheduler coroutines already running.

        The tool itself may be inside a non-cancellable OS thread.  Cancelling
        the asyncio wrapper prevents a stale success from reaching the model;
        the shared process registry/ExecutionService is responsible for killing
        owned child processes separately.
        """
        queued = self.cancel_queued()
        running = 0
        for task, task_id in list(self._running_tasks.items()):
            if not task.done():
                self._cancelled_running.add(task_id)
                task.cancel()
                running += 1
        return {"queued": queued, "running": running}

    async def _execute(self, spec: TaskSpec) -> TaskResult:
        # A queued-cancel click can land between task creation and first run.
        if self._states[spec.task_id]["status"] == "cancelled":
            return TaskResult(spec.task_id, "cancelled")
        attempts = 0
        self._update(spec.task_id, "running")
        while True:
            attempts += 1
            self._update(spec.task_id, "running", attempts=attempts)
            try:
                if spec.exclusive:
                    async with self._exclusive_lock:
                        value = await spec.run()
                else:
                    value = await spec.run()
                self._update(spec.task_id, "succeeded")
                return TaskResult(spec.task_id, "succeeded", value=value, attempts=attempts)
            except asyncio.CancelledError:
                # Thread-based OS actions might continue, but this scheduler
                # coroutine must never claim their eventual result succeeded.
                self._update(spec.task_id, "interrupted")
                if spec.task_id in self._cancelled_running:
                    self._cancelled_running.discard(spec.task_id)
                    return TaskResult(
                        spec.task_id, "interrupted",
                        error="Interrupted by the global kill switch",
                        attempts=attempts,
                    )
                raise
            except Exception as exc:
                if (spec.retry_safe and not isinstance(exc, TaskReportedFailure)
                        and attempts <= spec.retry_limit):
                    await asyncio.sleep(min(0.25 * attempts, 1.0))
                    continue
                status = exc.status if isinstance(exc, TaskReportedFailure) else "failed"
                self._update(spec.task_id, status)
                return TaskResult(
                    spec.task_id, status,
                    value=exc.response if isinstance(exc, TaskReportedFailure) else None,
                    error=f"{type(exc).__name__}: {exc}",
                    attempts=attempts,
                )

    async def run_batch(self, specs: list[TaskSpec]) -> list[TaskResult]:
        """Run a dependency graph, returning results in submitted order."""
        if not specs:
            return []

        identifiers = [spec.task_id for spec in specs]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Task IDs must be unique within a batch")
        if any(task_id in self._states for task_id in identifiers):
            raise ValueError("Task IDs must be unique across batches")

        # Bound completed history; never remove a task still pending/running.
        if len(self._states) > 80:
            for key in list(self._states):
                if len(self._states) <= 60:
                    break
                if self._states[key]["status"] in _TERMINAL:
                    del self._states[key]

        by_id = {spec.task_id: spec for spec in specs}
        index = {spec.task_id: pos for pos, spec in enumerate(specs)}
        for spec in specs:
            self._states[spec.task_id] = {
                "id": spec.task_id,
                "label": spec.label[:110],
                "status": "queued",
                "attempts": 0,
            }
        self._notify()

        pending = set(identifiers)
        finished: dict[str, TaskResult] = {}
        running: dict[asyncio.Task, str] = {}

        try:
            while pending or running:
                # Remove cancelled and invalid-dependent jobs BEFORE starting work.
                for key in list(pending):
                    spec = by_id[key]
                    if self._states[key]["status"] == "cancelled":
                        finished[key] = TaskResult(key, "cancelled")
                        pending.remove(key)
                    elif any(dep not in by_id for dep in spec.depends_on):
                        self._update(key, "blocked")
                        finished[key] = TaskResult(key, "blocked", error="Missing task dependency")
                        pending.remove(key)
                    elif any(
                        dep in finished and finished[dep].status != "succeeded"
                        for dep in spec.depends_on
                    ):
                        self._update(key, "blocked")
                        finished[key] = TaskResult(key, "blocked", error="Dependency did not succeed")
                        pending.remove(key)

                ready = sorted(
                    (
                        by_id[key] for key in pending
                        if all(dep in finished for dep in by_id[key].depends_on)
                    ),
                    key=lambda spec: (spec.priority, index[spec.task_id]),
                )
                for spec in ready[: max(0, self.max_concurrency - len(running))]:
                    pending.remove(spec.task_id)
                    task = asyncio.create_task(self._execute(spec))
                    running[task] = spec.task_id
                    self._running_tasks[task] = spec.task_id

                if not running:
                    if pending:
                        # Cyclic graph: never execute a task whose prerequisites
                        # cannot be established.
                        for key in pending:
                            self._update(key, "blocked")
                            finished[key] = TaskResult(key, "blocked", error="Dependency cycle")
                        pending.clear()
                    break

                done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    key = running.pop(task)
                    self._running_tasks.pop(task, None)
                    try:
                        finished[key] = task.result()
                    except asyncio.CancelledError:
                        if key in self._cancelled_running:
                            self._cancelled_running.discard(key)
                            self._update(key, "interrupted")
                            finished[key] = TaskResult(
                                key, "interrupted",
                                error="Interrupted by the global kill switch",
                            )
                        else:
                            raise
        except asyncio.CancelledError:
            # Only pending tasks can be safely cancelled. Running tasks can
            # outlive the Live session and will report their own final state.
            for key in pending:
                self._update(key, "cancelled")
            raise

        return [finished[key] for key in identifiers]

