"""Small, privacy-conscious task presentation adapter for the existing EDITH UI.

Transforms scheduler metadata into bounded labels and statuses. No tool arguments,
tool results, file contents, or API settings are accepted by the view.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_VALID_STATES = frozenset({
    "queued", "running", "succeeded", "failed", "cancelled",
    "blocked", "interrupted",
})
_PRIORITY = {
    "running": 0, "queued": 1, "failed": 2, "interrupted": 3,
    "blocked": 4, "cancelled": 5, "succeeded": 6,
}
_TERMINAL = frozenset({"succeeded", "failed", "cancelled", "blocked", "interrupted"})


def compact_task_view(states: Iterable[Mapping], limit: int = 4) -> dict:
    """Return bounded plain text for a compact task panel; never invent progress.

    Running and waiting actions come first; completed history appears newest
    first. The input must be trusted scheduler metadata (not raw tool args).
    """
    if not 1 <= limit <= 8:
        raise ValueError("Task panel limit must be between 1 and 8")
    entries: list[dict] = []
    for item in states:
        status = str(item.get("status", "")).lower()
        if status not in _VALID_STATES:
            continue
        label = re.sub(r"[\x00-\x1f\x7f]+", " ", str(item.get("label") or "Task"))
        label = re.sub(r"\s+", " ", label).strip() or "Task"
        label = label[:74] + "…" if len(label) > 75 else label
        entries.append({"label": label, "status": status})

    indexed = list(enumerate(entries))
    indexed.sort(key=lambda pair: (
        _PRIORITY[pair[1]["status"]],
        -pair[0] if pair[1]["status"] in _TERMINAL else pair[0],
    ))
    return {
        "running": sum(e["status"] == "running" for e in entries),
        "queued": sum(e["status"] == "queued" for e in entries),
        "completed": sum(e["status"] == "succeeded" for e in entries),
        "failed": sum(e["status"] in {"failed", "blocked", "interrupted"} for e in entries),
        "total": len(entries),
        "visible": [e for _, e in indexed[:limit]],
    }
