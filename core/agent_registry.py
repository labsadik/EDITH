"""Local versioned agent manifest and opt-out enable/disable registry."""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "agents" / "manifest.json"
CONFIG_PATH = ROOT / "config" / "agents.json"
_LOCK = threading.RLock()
_AGENT_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

# A disabled agent's tools are not advertised to the voice model.
TOOL_AGENT_MAP: dict[str, str] = {
    "dev_agent": "software_development", "code_helper": "software_development",
    "browser_control": "browser_computer", "computer_control": "browser_computer",
    "screen_process": "browser_computer", "open_app": "browser_computer",
    "file_controller": "file_workspace", "file_processor": "file_workspace",
    "web_search": "research", "flight_finder": "research",
    "system_status": "system_monitor", "performance_metrics": "system_monitor",
    "platform_system": "system_monitor", "device_security": "device_security",
    "smart_network": "smart_network",
}


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(fallback)) else fallback
    except (OSError, ValueError, TypeError):
        return fallback


def _manifest() -> dict[str, dict[str, Any]]:
    payload = _read_json(MANIFEST_PATH, {})
    items = payload.get("agents", []) if isinstance(payload, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or "")
        version = str(item.get("version") or "")
        if not _AGENT_ID.fullmatch(identifier) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
            continue
        result[identifier] = dict(item)
    return result


def _read_settings() -> dict[str, Any]:
    data = _read_json(CONFIG_PATH, {})
    if not isinstance(data, dict):
        return {}
    enabled = data.get("enabled")
    return {"enabled": enabled if isinstance(enabled, dict) else {}}


def _write_settings(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CONFIG_PATH.parent,
            prefix=".edith-agents-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(CONFIG_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def list_agents(include_disabled: bool = True) -> list[dict[str, Any]]:
    """Return agent versions and runtime state from the shipped manifest + local toggles."""
    with _LOCK:
        manifest, settings = _manifest(), _read_settings()
        result = []
        for identifier, spec in manifest.items():
            enabled = bool(settings["enabled"].get(identifier, spec.get("default_enabled", True)))
            if not include_disabled and not enabled:
                continue
            result.append({
                "id": identifier,
                "name": str(spec.get("name") or identifier),
                "version": str(spec.get("version") or "0.0.0"),
                "module": str(spec.get("module") or ""),
                "description": str(spec.get("description") or ""),
                "capabilities": list(spec.get("capabilities") or []),
                "enabled": enabled,
                "status": "enabled" if enabled else "disabled",
            })
        return result


def get_agent(agent_id: str) -> dict[str, Any] | None:
    identifier = str(agent_id or "").strip().lower()
    return next((item for item in list_agents() if item["id"] == identifier), None)


def is_agent_enabled(agent_id: str) -> bool:
    item = get_agent(agent_id)
    return bool(item and item["enabled"])


def set_agent_enabled(agent_id: str, enabled: bool) -> dict[str, Any]:
    identifier = str(agent_id or "").strip().lower()
    with _LOCK:
        manifest = _manifest()
        if identifier not in manifest:
            raise KeyError(f"Unknown agent id: {identifier or '(empty)'}")
        settings = _read_settings()
        flags = dict(settings.get("enabled") or {})
        flags[identifier] = bool(enabled)
        settings["enabled"] = flags
        _write_settings(settings)
    return get_agent(identifier) or {"id": identifier, "enabled": bool(enabled)}


def filter_tool_declarations(declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide tools belonging to disabled agents; agent_manager remains available."""
    result = []
    for declaration in declarations:
        name = str(declaration.get("name") or "")
        agent_id = TOOL_AGENT_MAP.get(name)
        if agent_id is None or is_agent_enabled(agent_id):
            result.append(declaration)
    return result


def build_agent_prompt_context() -> str:
    agents = list_agents(include_disabled=True)
    lines = ["[VERSIONED AGENT RUNTIME]", "Use only enabled agents. Do not claim an agent capability that the manifest does not list."]
    for item in agents:
        state = "ENABLED" if item["enabled"] else "DISABLED"
        lines.append(f"- {item['id']} v{item['version']} [{state}]: {item['description']}")
    lines.append("All specialist text reasoning uses the single Powerful Brain profile. Gemini Live is the voice/audio transport and immediate conversation controller, not a second text brain.")
    lines.append("The Software Development agent combines development, DevOps and DevSecOps. It must run generated project commands only through the local Rust sandbox. Device Security is a read-only posture auditor. Smart Network only lists OS-known local neighbors; remote control requires authenticated pairing and a dedicated adapter.")
    return "\n".join(lines)


def format_agent_catalog() -> str:
    agents = list_agents()
    lines = ["EDITH agent catalog:"]
    for item in agents:
        lines.append(f"- {item['name']} · {item['id']} · v{item['version']} · {item['status']}")
        lines.append("  Capabilities: " + ", ".join(item["capabilities"]))
    return "\n".join(lines)


__all__ = [
    "TOOL_AGENT_MAP", "build_agent_prompt_context", "filter_tool_declarations",
    "format_agent_catalog", "get_agent", "is_agent_enabled", "list_agents",
    "set_agent_enabled",
]
