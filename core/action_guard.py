"""Action-level confirmation policy for destructive or externally visible operations.

This module never blocks an action on its own; it explains when EDITH must obtain
an explicit local confirmation before passing the request to an action handler.
"""
from __future__ import annotations

import json
import re
from pathlib import PurePath
from urllib.parse import urlsplit


_DESTRUCTIVE_TERMINAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("recursive file deletion", re.compile(r"\brm\s+-(?:[a-z]*r[a-z]*f|[a-z]*f[a-z]*r)\b", re.I)),
    ("Windows permanent file deletion", re.compile(r"\b(?:del|erase)\b[^\r\n]{0,100}/(?:f|q|s)\b", re.I)),
    ("recursive directory deletion", re.compile(r"\b(?:rmdir|rd)\s+/s\b", re.I)),
    ("PowerShell recursive deletion", re.compile(r"\bremove-item\b[^\r\n]{0,160}(?:-recurse|-force)", re.I)),
    ("disk formatting or wiping", re.compile(r"\b(?:format\s+[a-z]:|diskpart\b|clean\s+all\b|wipefs\b)", re.I)),
    ("system shutdown or restart", re.compile(r"\b(?:shutdown(?:\.exe)?|restart-computer|stop-computer)\b", re.I)),
    ("forced process termination", re.compile(r"\b(?:taskkill\b[^\r\n]{0,100}/f\b|kill\s+-9\b|stop-process\b[^\r\n]{0,100}-force\b)", re.I)),
    ("Docker or container deletion", re.compile(r"\b(?:docker|podman)\s+(?:rm|rmi|volume\s+rm|system\s+prune)\b", re.I)),
    ("cluster resource deletion", re.compile(r"\bkubectl\s+delete\b|\bterraform\s+destroy\b", re.I)),
    ("database or collection deletion", re.compile(r"\b(?:delete\s+from|drop\s+(?:database|table|collection|schema)|truncate\s+(?:table|collection))\b|\bdb\.[\w$]+\.(?:deleteMany|drop|remove)\s*\(|\bdb\.(?:dropDatabase|dropCollection)\s*\(", re.I)),
    ("application uninstall", re.compile(r"\b(?:winget\s+uninstall|choco\s+uninstall|brew\s+uninstall|adb\s+uninstall|apt(?:-get)?\s+(?:remove|purge))\b", re.I)),
    ("force-push or destructive git cleanup", re.compile(r"\bgit\s+(?:push\b[^\r\n]{0,100}--force|clean\b[^\r\n]{0,50}-[a-z]*f)", re.I)),
    ("package publication", re.compile(r"\b(?:npm|pnpm|yarn)\s+publish\b", re.I)),
)

_DESTRUCTIVE_TARGET = re.compile(
    r"\b(delete|delete permanently|permanently delete|remove|uninstall|terminate|kill|"
    r"drop database|drop table|truncate|format|factory reset|wipe|erase|revoke access|"
    r"delete account|close account|send|submit|publish|deploy)\b",
    re.I,
)


def _text(value: object, limit: int = 140) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _target_path(params: dict) -> str:
    path = _text(params.get("path") or "unspecified location", 90)
    name = _text(params.get("name") or "", 90)
    if name:
        # Avoid inventing an absolute path when the original tool uses shortcuts.
        clean_path = path.rstrip("/\\")
        clean_name = name.lstrip("/\\")
        return f"{clean_path}/{clean_name}"
    return path


def _explicit_window_target(parameters: dict | None = None) -> str:
    """Extract a named window/app from a close request without inventing a target."""
    p = parameters or {}
    for key in ("_confirmation_window_target", "title", "window_title", "app_name"):
        value = _text(p.get(key) or "", 120)
        if value:
            return value

    description = _text(p.get("description") or "", 180)
    if not description:
        return ""
    target = re.sub(
        r"^\s*(?:please\s+)?(?:close|terminate|kill|quit|exit|stop)\s+"
        r"(?:(?:the|my)\s+)?",
        "",
        description,
        flags=re.I,
    ).strip(" .,:;")
    target = re.sub(r"\s+(?:app|application|window|program|process)$", "", target, flags=re.I).strip()
    if target.casefold() in {
        "", "active", "current", "active app", "current app", "active application",
        "current application", "active window", "current window", "app", "application",
        "window", "program", "process", "the app", "the application", "the window",
    }:
        return ""
    return _text(target, 120)


def confirmation_requirement(tool_name: str, parameters: dict | None = None) -> str | None:
    """Return a user-facing confirmation description, or None for ordinary actions.

    A positive model/tool argument such as confirmed=yes is intentionally ignored.
    The dispatcher must obtain approval from the user's local UI before executing.
    """
    p = parameters or {}
    name = _text(tool_name, 50).lower()
    action = _text(p.get("action") or "", 50).lower().replace("-", "_").replace(" ", "_")
    description = _text(p.get("description") or "", 240).lower()

    # Some single-action OS requests arrive as natural-language descriptions
    # and are translated to an action inside the handler; guard them beforehand.
    if name == "computer_settings" and not action:
        if re.search(r"\b(shut\s*down|power\s*off|turn\s*off\s+(?:the\s+)?computer)\b", description):
            action = "shutdown"
        elif re.search(r"\b(restart|reboot)\b", description):
            action = "restart"
        elif re.search(r"\b(close|terminate|kill|quit|exit)\b", description):
            action = "close_app"

    if name == "file_controller" and action in {"delete", "delete_permanent", "permanent_delete"}:
        target = _target_path(p)
        if action in {"delete_permanent", "permanent_delete"}:
            return (
                f"PERMANENTLY delete '{target}' from disk? This cannot be undone. "
                "Confirm only if this is the exact file or folder you intend to remove."
            )
        return (
            f"Move '{target}' to the system Trash/Recycle Bin? Confirm only if this is the exact target."
        )

    if name == "computer_settings" and action in {"restart", "shutdown", "close_app", "close_window"}:
        if action == "restart":
            return "Restart this computer? Unsaved work may be lost. Confirm before restarting."
        if action == "shutdown":
            return "Shut down this computer? Unsaved work may be lost. Confirm before powering off."
        target = _explicit_window_target(p) or "the active application/window"
        if action == "close_app":
            return f"Close/terminate '{target}'? Unsaved work may be lost. Confirm only if this is the exact target."
        return f"Close the window '{target}'? Unsaved work may be lost. Confirm only if this is the exact target."

    if name == "send_message":
        platform = _text(p.get("platform") or "messaging app", 35)
        receiver = _text(p.get("receiver") or "unspecified recipient", 65)
        body = str(p.get("message_text") or p.get("text") or "").strip()
        return (
            f"Send a message using {platform} to '{receiver}'?\n\n"
            f"Message to review:\n{body or '[No message body provided]'}\n\n"
            "This preview is shown only in the local confirmation dialog, not in the Activity Log."
        )

    if name == "desktop_control" and action in {"clean", "delete", "remove"}:
        target = _text(p.get("path") or p.get("task") or "desktop items", 110)
        return f"Run the desktop cleanup/removal operation for '{target}'? Confirm before items are moved or removed."

    if name == "smart_network" and action in {"control", "write"}:
        entity = _text(p.get("entity_id") or "unspecified Home Assistant entity", 90)
        service = _text(p.get("service") or "unspecified service", 60)
        details = p.get("service_data") or {}
        preview = _text(json.dumps(details, ensure_ascii=False, sort_keys=True), 220)
        return (
            f"Change paired smart-home device '{entity}' using '{service}'? "
            f"Settings: {preview}. Confirm only if this is the intended device and state change."
        )

    if name == "knowledge_base" and action == "index_file":
        target = _text(p.get("file_path") or "the selected local document", 140)
        return (
            f"Read '{target}' and index its contents in EDITH's local vector database? "
            "Document text will remain on this device and will not be uploaded to an embedding service."
        )

    if name in {"browser_control", "computer_control"}:
        if action in {"click", "smart_click", "screen_click", "right_click", "double_click"}:
            target = _text(p.get("description") or p.get("text") or p.get("selector") or "", 120)
            if target and _DESTRUCTIVE_TARGET.search(target):
                return (
                    f"Activate this potentially destructive control: '{target}'? "
                    "Confirm only after the current screen shows the intended target."
                )

    if name in {"browser_control", "computer_control", "computer_settings"}:
        key_name = _text(p.get("key") or p.get("value") or "", 40).lower().replace(" ", "_")
        if action in {"press_key", "key_press", "press"} and key_name in {"delete", "del", "shift+delete", "shift_del"}:
            return (
                f"Press the {key_name} key in the current app? This may remove the selected item. "
                "Confirm only after checking the visible target."
            )

    if (
        name in {"browser_control", "computer_control", "computer_settings"}
        and action in {"type", "smart_type", "paste", "type_text", "write_on_screen", "write"}
    ):
        command_text = str(p.get("text") or p.get("value") or "")
        for label, pattern in _DESTRUCTIVE_TERMINAL_PATTERNS:
            if pattern.search(command_text):
                review_text = str(command_text).strip()
                if len(review_text) > 6000:
                    review_text = review_text[:6000] + "\n[Preview truncated; a truncated preview must not authorize execution.]"
                return (
                    f"Run this high-impact operation ({label}) in the target application?\n\n"
                    f"Exact command/text to review:\n{review_text}\n\n"
                    "Confirm only if the target and every operation shown above are intended."
                )

    # Coding execution confirms the exact source/argv in core.execution, including
    # build and file_processor paths. Do not show a duplicate generic prompt here.

    return None


__all__ = ["confirmation_requirement"]

