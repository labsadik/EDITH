"""Phase 6: conservative action verification and privacy-safe task recovery.

The journal stores *only* generated task IDs, tool names, lifecycle states and
duration. It deliberately never stores prompts, arguments, paths, tool output,
message bodies, tokens or API credentials. Interrupted tasks are NEVER replayed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import sys
import time
from collections import OrderedDict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.action_activity import activity_outcome
from core.task_scheduler import parallel_read_only


@dataclass(frozen=True)
class ActionEvidence:
    """Conservative interpretation of a tool response, not an OS-level proof."""

    status: str  # reported, unverified, failed, cancelled
    verification: str  # tool_reported, follow_up_required, not_verified
    blocks_dependents: bool

    def response_metadata(self) -> dict[str, str]:
        return {
            "status": self.status,
            "verification": self.verification,
            "guidance": (
                "Do not repeat the action automatically. Verify its actual effect "
                "with a separate read-only observation before claiming completion."
                if self.verification == "follow_up_required" else
                "This action has no confirmed successful result. Do not start dependent actions."
                if self.blocks_dependents else
                "The result was supplied by the tool; do not invent additional outcomes."
            ),
        }


_SIDE_EFFECT_TOOLS = frozenset({
    "open_app", "file_controller", "browser_control", "computer_control",
    "computer_settings", "desktop_control", "send_message", "reminder",
    "code_helper", "dev_agent", "game_updater", "save_memory",
    "manage_monitor", "set_voice_mode", "shutdown_edith", "close_camera",
})
_UNCERTAIN_PHRASES = (
    "could not verify", "not confirmed", "verification pending",
    "completion cannot be verified", "delivery is unverified",
    "not independently verified", "launch request submitted",
    "request submitted", "no delivery receipt",
    "without a detailed result",
)


def assess_action_evidence(
    tool_name: str,
    args: Mapping[str, Any] | None,
    result: object,
) -> ActionEvidence:
    """Fail closed for explicit errors and missing receipts; never guess success."""
    text = str(result or "").strip()
    normalized = text.casefold()
    if "cancelled by user" in normalized or normalized.startswith("cancelled while queued"):
        return ActionEvidence("cancelled", "not_verified", True)
    if not text or normalized in {"done.", "done", "completed.", "completed"}:
        return ActionEvidence("unverified", "not_verified", True)
    if any(fragment in normalized for fragment in _UNCERTAIN_PHRASES):
        return ActionEvidence("unverified", "not_verified", True)
    outcome = activity_outcome(text)
    if outcome == "error":
        return ActionEvidence("failed", "not_verified", True)
    if outcome == "warning":
        return ActionEvidence("unverified", "not_verified", True)
    if tool_name in _SIDE_EFFECT_TOOLS and not parallel_read_only(tool_name, args):
        # A handler acknowledging its own action is not independent validation.
        return ActionEvidence("reported", "follow_up_required", False)
    return ActionEvidence("reported", "tool_reported", False)


class ActionDeduplicator:
    """Suppress repeated non-read-only function calls by provider call ID.

    Only an HMAC digest of arguments is held in bounded process memory. A
    repeated ID is never re-executed, even when the submitted arguments differ.
    A missing ID cannot safely identify a duplicate, so it is not registered.
    """

    def __init__(self, limit: int = 512):
        if not 1 <= limit <= 4096:
            raise ValueError("limit must be between 1 and 4096")
        self._secret = secrets.token_bytes(32)
        self._seen: OrderedDict[str, bytes] = OrderedDict()
        self._limit = limit

    def reserve(self, call_id: str | None, tool_name: str, args: Mapping[str, Any] | None) -> str:
        if not call_id:
            return "untracked"
        key = str(call_id)[:256]
        payload = json.dumps(
            {"tool": tool_name, "args": args or {}},
            sort_keys=True, ensure_ascii=False, default=str,
        ).encode("utf-8")
        digest = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if key in self._seen:
            return "duplicate" if hmac.compare_digest(self._seen[key], digest) else "conflict"
        self._seen[key] = digest
        if len(self._seen) > self._limit:
            self._seen.popitem(last=False)
        return "new"


def _safe_tool_name(tool: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", str(tool).lower())[:60] or "unknown"


class AgentTaskJournal:
    """Bounded SQLite record of outcomes, with crash-safe no-replay recovery."""

    _TERMINAL = frozenset({"succeeded", "failed", "cancelled", "blocked", "interrupted"})

    def __init__(self, path: Path | None = None, retention: int = 300):
        if not 10 <= retention <= 10000:
            raise ValueError("retention must be between 10 and 10000")
        self.path = Path(path) if path is not None else (
            (Path(sys.executable).parent if getattr(sys, "frozen", False)
             else Path(__file__).resolve().parents[1]) / "memory" / "agent_history.sqlite3"
        )
        self.retention = retention
        self.available = self._initialize()

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=1.0)

    def _initialize(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection:
                with connection:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS tasks ("
                        "task_id TEXT PRIMARY KEY, tool TEXT NOT NULL, "
                        "status TEXT NOT NULL, verification TEXT NOT NULL DEFAULT 'not_verified', "
                        "duration_ms INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL)"
                    )
                    # Existing jobs might have been executing during a crash.
                    # Mark as interrupted; never infer success or auto-resume.
                    connection.execute(
                        "UPDATE tasks SET status='interrupted', verification='not_verified', "
                        "updated_at=? WHERE status IN ('queued', 'running')", (time.time(),)
                    )
            return True
        except (OSError, sqlite3.Error):
            return False

    def plan(self, tasks: list[tuple[str, str]]) -> bool:
        if not self.available:
            return False
        try:
            now = time.time()
            with closing(self._connect()) as connection:
                with connection:
                    connection.executemany(
                        "INSERT INTO tasks (task_id, tool, status, created_at, updated_at) "
                        "VALUES (?, ?, 'queued', ?, ?)",
                        [(str(task_id)[:96], _safe_tool_name(tool), now, now)
                         for task_id, tool in tasks],
                    )
            return True
        except (OSError, sqlite3.Error):
            return False

    def started(self, task_id: str) -> bool:
        return self._set_status(task_id, "running", "not_verified", None)

    def finished(self, task_id: str, status: str, verification: str,
                 duration_ms: int | None = None) -> bool:
        if status not in self._TERMINAL:
            raise ValueError("Invalid terminal task status")
        if verification not in {"not_verified", "tool_reported", "follow_up_required"}:
            raise ValueError("Invalid verification level")
        return self._set_status(task_id, status, verification, duration_ms)

    def _set_status(self, task_id: str, status: str, verification: str,
                    duration_ms: int | None) -> bool:
        if not self.available:
            return False
        try:
            with closing(self._connect()) as connection:
                with connection:
                    connection.execute(
                        "UPDATE tasks SET status=?, verification=?, duration_ms=?, updated_at=? "
                        "WHERE task_id=?",
                        (status, verification, duration_ms, time.time(), task_id),
                    )
                    connection.execute(
                        "DELETE FROM tasks WHERE task_id IN (SELECT task_id FROM tasks "
                        "WHERE status IN ('succeeded','failed','cancelled','blocked','interrupted') "
                        "ORDER BY updated_at DESC, rowid DESC LIMIT -1 OFFSET ?)",
                        (self.retention,),
                    )
            return True
        except (OSError, sqlite3.Error):
            return False

    def recent(self, limit: int = 10) -> list[dict]:
        """Never returns tool inputs, outputs, labels, target names or credentials."""
        if not self.available:
            return []
        size = max(1, min(int(limit), 30))
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT tool, status, verification, duration_ms "
                    "FROM tasks ORDER BY created_at DESC, rowid DESC LIMIT ?",
                    (size,),
                ).fetchall()
            return [
                {"tool": tool, "status": status, "verification": verification,
                 "duration_ms": duration_ms}
                for tool, status, verification, duration_ms in rows
            ]
        except (OSError, sqlite3.Error):
            return []


def format_task_history(items: list[dict]) -> str:
    """User-visible sanitized summary; no raw tool messages or paths."""
    if not items:
        return "No completed or interrupted task history is available yet."
    lines = ["Recent EDITH task history (tool names/status only, newest first):"]
    for item in items[:15]:
        tool = _safe_tool_name(item.get("tool", "unknown"))
        status = str(item.get("status") or "unknown")
        verification = str(item.get("verification") or "not_verified")
        lines.append(f"- {tool}: {status} ({verification})")
    lines.append(
        "Tool-reported success is not independent visual/OS verification. "
        "Interrupted operations are not automatically repeated."
    )
    return "\n".join(lines)
