"""Safe, user-visible descriptions for EDITH desktop and browser actions.

Only action metadata is summarized here. Text entered into fields, message bodies,
clipboard contents, credentials, and file contents are intentionally not logged.
"""
from __future__ import annotations

import re
from pathlib import PurePath
from urllib.parse import urlsplit


def _clean(value: object, limit: int = 90) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _url_target(value: object) -> str:
    """Show a destination without query parameters or fragments (which may be sensitive)."""
    raw = _clean(value, 240)
    try:
        parts = urlsplit(raw)
        if not parts.scheme or not parts.hostname:
            return _clean(raw, 90)
        host = parts.hostname
        if parts.port:
            host = f"{host}:{parts.port}"
        return _clean(f"{parts.scheme}://{host}{parts.path}", 90)
    except (ValueError, TypeError):
        return _clean(raw, 90)


def _basename(value: object) -> str:
    raw = _clean(value, 180)
    return _clean(PurePath(raw.replace("\\", "/")).name or raw, 70)


def describe_tool_activity(tool_name: str, args: dict | None = None) -> str:
    """Return a short, privacy-conscious label for a tool about to run."""
    p = args or {}
    name = _clean(tool_name, 40).lower()
    action = _clean(p.get("action", ""), 30).lower()

    if name == "open_app":
        if action in {"list", "list_installed", "discover"}:
            return "Discover installed desktop app launchers"
        if action in {"search", "find"}:
            query = _clean(p.get("query") or p.get("app_name") or "", 65)
            return f"Search installed desktop app launchers{f': {query}' if query else ''}"
        return f"Open desktop app: {_clean(p.get('app_name') or 'unspecified app', 70)}"

    if name == "browser_control":
        browser = _clean(p.get("browser") or "default browser", 28)
        if action == "search":
            return f"Search in {browser}: {_clean(p.get('query') or '', 65)}"
        if action in {"go_to", "new_tab"}:
            return f"Navigate {browser} to {_url_target(p.get('url') or '')}"
        if action in {"click", "smart_click"}:
            target = p.get("description") or p.get("text") or p.get("selector") or "page element"
            return f"Click in {browser}: {_clean(target, 65)}"
        if action in {"type", "smart_type"}:
            target = p.get("description") or p.get("selector") or "active field"
            count = len(str(p.get("text") or ""))
            return f"Enter text in {browser} ({_clean(target, 45)}; {count} characters; content hidden)"
        if action == "fill_form":
            fields = p.get("fields")
            count = len(fields) if isinstance(fields, dict) else 0
            return f"Fill {count} form field(s) in {browser}; values hidden"
        if action == "scroll":
            return f"Scroll {browser} {_clean(p.get('direction') or 'down', 12)}"
        if action:
            return f"Browser {browser}: {action.replace('_', ' ')}"
        return f"Browser action in {browser}"

    if name == "computer_control":
        if action in {"type", "smart_type", "paste"}:
            count = len(str(p.get("text") or ""))
            return f"Desktop: {_clean(action.replace('_', ' '), 25)} ({count} characters; content hidden)"
        if action in {"click", "left_click", "double_click", "right_click", "move"}:
            return f"Desktop: {action.replace('_', ' ')} at ({_clean(p.get('x', '?'), 12)}, {_clean(p.get('y', '?'), 12)})"
        if action in {"screen_find", "screen_click"}:
            target = _clean(p.get("description") or "screen element", 70)
            verb = "Find" if action == "screen_find" else "Find and click"
            return f"Desktop: {verb} '{target}'"
        if action == "focus_window":
            return f"Bring window to front: {_clean(p.get('title') or 'target window', 70)}"
        if action == "hotkey":
            return f"Desktop: press shortcut {_clean(p.get('keys') or '', 35)}"
        if action == "press":
            return f"Desktop: press {_clean(p.get('key') or 'enter', 24)}"
        if action == "scroll":
            return f"Desktop: scroll {_clean(p.get('direction') or 'down', 12)}"
        if action:
            return f"Desktop control: {action.replace('_', ' ')}"
        return "Desktop control action"

    if name == "computer_settings":
        detail = _clean(p.get("description") or "", 65)
        return f"Computer settings: {detail or action.replace('_', ' ') or 'control action'}"

    if name == "desktop_control":
        detail = _clean(p.get("task") or p.get("action") or "desktop task", 70)
        return f"Desktop management: {detail}"

    if name == "file_controller":
        location = _basename(p.get("path") or "")
        if action in {"move", "copy"}:
            destination = _basename(p.get("destination") or "")
            target = f"{location} → {destination}" if destination else location
        else:
            target = location
        return f"Files: {action.replace('_', ' ') or 'manage'}{f' — {target}' if target else ''}"

    if name == "send_message":
        platform = _clean(p.get("platform") or "messaging app", 28)
        receiver = _clean(p.get("receiver") or "recipient", 45)
        return f"Send message via {platform} to {receiver}; message content hidden"

    if name == "screen_process":
        mode = _clean(p.get("angle") or "screen", 20).lower()
        return "Inspect webcam view" if mode == "camera" else "Inspect current desktop screen"

    if name == "youtube_video":
        target = _clean(p.get("query") or "", 65)
        return f"YouTube: {action or 'play'}{f' — {target}' if target else ''}"

    if name in {"code_helper", "dev_agent"}:
        task = _clean(p.get("description") or p.get("task") or p.get("action") or "development task", 75)
        return f"{'Code helper' if name == 'code_helper' else 'Development agent'}: {task}"

    if name == "reminder":
        when = " ".join(_clean(p.get(k) or "", 20) for k in ("date", "time")).strip()
        return f"Set reminder{f' for {when}' if when else ''}"

    if name == "game_updater":
        game = _clean(p.get("game_name") or "games", 50)
        return f"Game manager: {action or 'check'} {game}"

    # Generic plugin/action: log the tool name and action only, never arbitrary values.
    label = _clean(tool_name.replace("_", " "), 45)
    return f"{label}: {action.replace('_', ' ') if action else 'run action'}"


def activity_outcome(result: object) -> str:
    """Classify tool outcome without copying arbitrary tool output into the activity log."""
    text = str(result or "").strip().lower()
    if not text:
        return "warning"
    if (
        "launch request submitted" in text
        or "could not verify that it opened" in text
        or "not confirmed as the foreground window" in text
    ):
        return "warning"
    failures = (
        "failed", "error:", "could not", "unknown tool", "unknown action",
        "not available", "not installed", "timed out", "permission denied",
        "element not found", "not found on screen", "unsupported operating system",
        "access denied", "path not found", "file not found", "source not found",
        "not a directory", "cancelled by user", "nothing was executed",
        "context or browser has been closed", "browser context closed",
    )
    if any(token in text for token in failures):
        return "error"
    cautions = (
        "no results", "no active", "not provided", "please specify",
        "might not be installed", "not sure", "ignored duplicate",
    )
    if any(token in text for token in cautions):
        return "warning"
    return "ok"
