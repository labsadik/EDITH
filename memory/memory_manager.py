"""Durable, backward-compatible long-term memory for EDITH.

All writes use a same-directory temporary file and atomic replacement. The
previous valid document is retained as ``long_term.json.bak`` so interrupted
writes or manual corruption can recover without erasing user facts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from threading import RLock
from pathlib import Path
import sys
import tempfile
import re
from typing import Any

from core.app_paths import app_data_dir, is_frozen


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = app_data_dir() if is_frozen() else get_base_dir()
MEMORY_PATH = BASE_DIR / "memory" / "long_term.json"
_lock = RLock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200
_SESSION_MAX = 3
_CATEGORIES = ("identity", "preferences", "projects", "relationships", "wishes", "notes")


def _empty_memory() -> dict[str, Any]:
    return {category: {} for category in _CATEGORIES}


def _backup_path(path: Path | None = None) -> Path:
    path = path or MEMORY_PATH
    return path.with_name(path.name + ".bak")


def _decode(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _normalise(memory: dict[str, Any] | None) -> dict[str, Any]:
    """Migrate old partial documents without discarding unrelated tool data."""
    result: dict[str, Any] = dict(memory or {})
    for category in _CATEGORIES:
        if not isinstance(result.get(category), dict):
            result[category] = {}
    sessions = result.get("sessions")
    if sessions is not None and not isinstance(sessions, list):
        result["sessions"] = []
    return result


def _encoded(memory: dict[str, Any]) -> str:
    return json.dumps(_normalise(memory), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _replace_atomically(path: Path, content: str, *, preserve_backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".edith-memory-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Preserve only a valid prior primary snapshot.
        if preserve_backup and path.exists():
            previous = _decode(path)
            if previous is not None:
                _replace_atomically(_backup_path(path), _encoded(previous), preserve_backup=False)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _load_locked(path: Path | None = None) -> dict[str, Any]:
    path = path or MEMORY_PATH
    if not path.exists():
        return _empty_memory()
    primary = _decode(path)
    if primary is not None:
        return _normalise(primary)
    backup = _decode(_backup_path(path))
    if backup is not None:
        recovered = _normalise(backup)
        _replace_atomically(path, _encoded(recovered), preserve_backup=False)
        print("[Memory] Recovered long-term memory from the last valid backup.")
        return recovered
    print("[Memory] Load error: primary and backup are unreadable; using empty memory.")
    return _empty_memory()


def load_memory() -> dict[str, Any]:
    with _lock:
        return json.loads(json.dumps(_load_locked(), ensure_ascii=False))


def _all_entries(memory: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    entries = []
    for category, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((category, str(key), entry))
    return entries


def _trim_to_limit(memory: dict[str, Any]) -> dict[str, Any]:
    while len(_encoded(memory)) > MEMORY_MAX_CHARS:
        entries = _all_entries(memory)
        if not entries:
            break
        entries.sort(key=lambda item: str(item[2].get("updated", "0000-00-00")))
        category, key, _entry = entries[0]
        memory.get(category, {}).pop(key, None)
        print(f"[Memory] Trimmed {category}/{key}")
    return memory


def _save_locked(memory: dict[str, Any]) -> None:
    _replace_atomically(MEMORY_PATH, _encoded(_trim_to_limit(_normalise(memory))))


def save_memory(memory: dict[str, Any]) -> None:
    if not isinstance(memory, dict):
        return
    with _lock:
        _save_locked(memory)


def _truncate_value(value: str) -> str:
    return value[:MAX_VALUE_LENGTH].rstrip() + "…" if len(value) > MAX_VALUE_LENGTH else value


def _recursive_update(target: dict[str, Any], updates: dict[str, Any]) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if isinstance(value, dict) and "value" not in value:
            if not isinstance(target.get(key), dict):
                target[key] = {}; changed = True
            changed = _recursive_update(target[key], value) or changed
            continue
        new_value = _truncate_value(str(value.get("value") if isinstance(value, dict) else value))
        previous = target.get(key)
        if not isinstance(previous, dict) or previous.get("value") != new_value:
            target[key] = {"value": new_value, "updated": datetime.now().strftime("%Y-%m-%d")}
            changed = True
    return changed


def update_memory(memory_update: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    with _lock:
        memory = _load_locked()
        if _recursive_update(memory, memory_update):
            _save_locked(memory)
            print(f"[Memory] Saved: {list(memory_update.keys())}")
        return json.loads(json.dumps(memory, ensure_ascii=False))


def retrieve_memory(query: str = "", limit: int = 16) -> list[dict[str, str]]:
    """Return bounded, deterministic relevant facts without exposing raw storage."""
    with _lock:
        return _retrieve_from_memory(_load_locked(), query, limit)


def _retrieve_from_memory(memory: dict[str, Any], query: str = "", limit: int = 16) -> list[dict[str, str]]:
    """Rank facts from a supplied snapshot; callers never observe mutable entries."""
    words = {word.casefold() for word in re.findall(r"[\w\u0980-\u09ff]{3,}", query or "")}
    items: list[tuple[int, str, str, dict[str, str]]] = []
    for category, key, entry in _all_entries(_normalise(memory)):
        value = str(entry.get("value") or "")
        score = sum(word in f"{key} {value}".casefold() for word in words)
        items.append((score, str(entry.get("updated") or ""), category, {"key": key, "value": value}))
    items.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if words:
        items = [item for item in items if item[0] > 0]
    return [{"category": category, **entry} for _score, _date, category, entry in items[:max(1, min(64, int(limit)))]]


def format_memory_for_prompt(memory: dict[str, Any] | None, query: str = "") -> str:
    if not memory:
        return ""
    selected = _retrieve_from_memory(memory, query, limit=32) if query else [
        {"category": category, "key": key, "value": str(entry.get("value") or "")}
        for category, key, entry in _all_entries(_normalise(memory))
    ]
    grouped: dict[str, list[dict[str, str]]] = {category: [] for category in _CATEGORIES}
    for entry in selected:
        if entry["category"] in grouped and entry["value"]:
            grouped[entry["category"]].append(entry)
    lines: list[str] = []
    identity_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in identity_fields:
        lines.extend(f"{field.title()}: {entry['value']}" for entry in grouped["identity"] if entry["key"] == field)
    lines.extend(f"{entry['key'].replace('_', ' ').title()}: {entry['value']}" for entry in grouped["identity"] if entry["key"] not in identity_fields)
    headings = (("preferences", "Preferences:"), ("projects", "Active Projects / Goals:"),
                ("relationships", "People in their life:"), ("wishes", "Wishes / Plans / Wants:"),
                ("notes", "Other notes:"))
    for category, heading in headings:
        entries = grouped[category][:15]
        if entries:
            lines.extend(["", heading])
            lines.extend(f"  - {entry['key'].replace('_', ' ').title()}: {entry['value']}" for entry in entries)
    if not lines:
        return ""
    result = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n" + "\n".join(lines)
    return (result[:1997].rstrip() + "…" if len(result) > 2000 else result) + "\n"


def remember(key: str, value: str, category: str = "notes") -> str:
    category = category if category in _CATEGORIES else "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    with _lock:
        memory = _load_locked(); bucket = memory.get(category, {})
        if key not in bucket:
            return f"Not found: {category}/{key}"
        del bucket[key]; _save_locked(memory)
        return f"Forgotten: {category}/{key}"


forget_memory = forget


def save_session_summary(summary: str, language: str = "") -> None:
    summary = (summary or "").strip()
    if not summary:
        return
    with _lock:
        memory = _load_locked(); sessions = memory.get("sessions", [])
        sessions = sessions if isinstance(sessions, list) else []
        entry: dict[str, str] = {"date": datetime.now().strftime("%Y-%m-%d"), "summary": summary[:280]}
        if language:
            entry["language"] = language
        memory["sessions"] = [*sessions, entry][-_SESSION_MAX:]
        _save_locked(memory)
    print(f"[Memory] Session saved ({entry['date']}): {summary[:60]}…")


def pop_last_session() -> dict[str, Any] | None:
    with _lock:
        memory = _load_locked(); sessions = memory.get("sessions", [])
        if not isinstance(sessions, list) or not sessions:
            return None
        entry = sessions.pop(); memory["sessions"] = sessions; _save_locked(memory)
        return entry if isinstance(entry, dict) else None
