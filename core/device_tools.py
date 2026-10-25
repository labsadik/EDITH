"""Curated local-device bridge for the assistant's existing platform layer.

This module intentionally exposes diagnostics and a small set of local device
controls only.  It is not a network scanner, remote-access bridge, exploit
runner, or a generic command shell; the separately reviewed shell tool owns
command execution.  Calls retain the platform controller's structured result,
permission tiers, audit receipt and interrupt-aware child-process ownership.
"""
from __future__ import annotations

import json
from typing import Any

from edith.platform.audit import redact


_OPERATIONS = frozenset({
    "system_info", "telemetry", "network_info", "process_list", "window_list",
    "installed_apps", "capabilities", "hardware_inventory", "display_list",
    "audio_devices", "theme", "process_kill", "app_launch",
    "volume", "brightness", "power",
})

_ARGUMENTS = {
    "process_kill": {"pid"},
    "app_launch": {"app"},
    "volume": {"value"},
    "brightness": {"value"},
    "power": {"action"},
}

_REQUIRED = {
    "process_kill": {"pid"},
    "app_launch": {"app"},
    "volume": {"value"},
    "brightness": {"value"},
    "power": {"action"},
}


def _failure(message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": message, "unsupported": False}


def _bounded(value: Any) -> Any:
    """Keep results useful to a model/UI without handing over bulk local data."""
    if isinstance(value, str):
        return value[:12_000] + ("…" if len(value) > 12_000 else "")
    if isinstance(value, list):
        return [_bounded(item) for item in value[:120]]
    if isinstance(value, dict):
        # Defensive: binary screenshots or accidental binary fields never cross
        # this bridge. The platform screenshot API remains available to native UI
        # code but is deliberately not an LLM device-tool operation.
        return {
            str(key): (f"[omitted binary payload: {len(str(item))} chars]"
                       if str(key).casefold() in {"base64", "image", "bytes"}
                       else _bounded(item))
            for key, item in list(value.items())[:120]
        }
    return value


class DeviceToolService:
    """Validate tool input before it reaches ``SystemController.invoke``."""

    def __init__(self, controller):
        self.controller = controller

    @staticmethod
    def declared_operations() -> list[str]:
        return sorted(_OPERATIONS)

    def execute(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = payload or {}
        operation = str(payload.get("operation") or "").strip().lower()
        arguments = payload.get("arguments") or {}
        if operation not in _OPERATIONS:
            return _failure(
                "Unsupported local-device operation. Available operations: "
                + ", ".join(self.declared_operations())
            )
        if not isinstance(arguments, dict):
            return _failure("Device operation arguments must be an object.")
        allowed = _ARGUMENTS.get(operation, set())
        unexpected = sorted(set(arguments) - allowed)
        if unexpected:
            return _failure("Unexpected argument(s) for %s: %s" % (operation, ", ".join(unexpected)))
        missing = sorted(key for key in _REQUIRED.get(operation, set()) if arguments.get(key) is None)
        if missing:
            return _failure("Missing required argument(s) for %s: %s" % (operation, ", ".join(missing)))
        if operation == "process_kill":
            try:
                if int(arguments["pid"]) <= 1:
                    return _failure("Use a positive non-system process ID.")
            except (TypeError, ValueError):
                return _failure("Process ID must be an integer.")
        if operation in {"volume", "brightness"}:
            try:
                value = int(arguments["value"])
            except (TypeError, ValueError):
                return _failure("Volume and brightness must be an integer from 0 through 100.")
            if not 0 <= value <= 100:
                return _failure("Volume and brightness must be between 0 and 100.")
            arguments = {"value": value}
        if operation == "power" and arguments.get("action") not in {"sleep", "restart", "shutdown"}:
            return _failure("Power action must be sleep, restart, or shutdown.")
        if operation == "app_launch" and not str(arguments.get("app") or "").strip():
            return _failure("Application name is required.")

        receipt = self.controller.invoke(operation, arguments)
        return {
            "ok": bool(receipt.get("ok")),
            "data": _bounded(redact(receipt.get("data"))),
            "error": str(receipt.get("error") or "")[:1200] or None,
            "unsupported": bool(receipt.get("unsupported")),
        }


def format_device_result(receipt: dict[str, Any]) -> str:
    """Stable bounded text for a function response and the Activity panel."""
    if not receipt.get("ok"):
        label = "Unavailable" if receipt.get("unsupported") else "Device action failed"
        return f"{label}: {receipt.get('error') or 'No detail was returned.'}"
    return json.dumps(receipt.get("data"), ensure_ascii=False, indent=2, default=str)[:18_000]


__all__ = ["DeviceToolService", "format_device_result"]

