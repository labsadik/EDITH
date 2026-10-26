"""Canonical EDITH tool catalogue and conservative retry/fallback policy.

The registry has no execution privileges.  It makes the Live model's declared
tools, scheduler policy, and fallback decisions use the same view of the
available built-ins, local commands, Python plugins and configured MCP plugins.
Unknown tools always stay sequential and are never retried automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping


@dataclass(frozen=True)
class ToolDescriptor:
    """A normalised declaration plus the narrow policy applicable to a tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    source: str = "builtin"  # builtin | local_command | plugin | mcp
    read_only: bool = False
    retry_limit: int = 0
    fallback_name: str = ""
    fallback_arguments: Mapping[str, Any] | None = None

    def declaration(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass(frozen=True)
class FallbackCandidate:
    name: str
    arguments: dict[str, Any]
    source: str


class ToolRegistry:
    """Refreshable, side-effect-safe policy registry.

    Plugin availability is read each time ``descriptors`` is requested.  That
    keeps the existing Plugin Manager toggles live without reloading modules.
    """

    _READ_ONLY_BUILTINS = frozenset({
        "web_search", "system_status", "performance_metrics", "task_history",
    })
    _RETRYABLE_READS = frozenset({"web_search", "system_status", "performance_metrics"})

    def __init__(
        self,
        builtin_declarations: Iterable[Mapping[str, Any]],
        plugin_declarations: Callable[[], Iterable[Mapping[str, Any]]],
    ) -> None:
        self._plugins = plugin_declarations
        self._builtins: dict[str, ToolDescriptor] = {}
        for declaration in builtin_declarations:
            name = str(declaration.get("name") or "").strip()
            if not name:
                continue
            source = "local_command" if name == "shell_execute" else "builtin"
            read_only = name in self._READ_ONLY_BUILTINS
            retry_limit = 1 if name in self._RETRYABLE_READS else 0
            fallback_name = "platform_system" if name == "system_status" else ""
            fallback_arguments = {"operation": "telemetry"} if fallback_name else None
            self._builtins[name] = ToolDescriptor(
                name=name,
                description=str(declaration.get("description") or ""),
                parameters=dict(declaration.get("parameters") or {}),
                source=source,
                read_only=read_only,
                retry_limit=retry_limit,
                fallback_name=fallback_name,
                fallback_arguments=fallback_arguments,
            )

    def descriptors(self) -> list[ToolDescriptor]:
        """Return declarations with the presently enabled plugin list included."""
        dynamic: dict[str, ToolDescriptor] = {}
        try:
            plugin_declarations = self._plugins() or ()
        except Exception:
            plugin_declarations = ()
        for declaration in plugin_declarations:
            name = str(declaration.get("name") or "").strip()
            if not name or name in self._builtins:
                continue
            dynamic[name] = ToolDescriptor(
                name=name,
                description=str(declaration.get("description") or ""),
                parameters=dict(declaration.get("parameters") or {}),
                source="mcp" if name.startswith("mcp_") else "plugin",
            )
        return [*self._builtins.values(), *dynamic.values()]

    def declarations(self) -> list[dict[str, Any]]:
        return [descriptor.declaration() for descriptor in self.descriptors()]

    def get(self, name: str) -> ToolDescriptor | None:
        for descriptor in self.descriptors():
            if descriptor.name == name:
                return descriptor
        return None

    def policy(self, name: str) -> tuple[bool, int]:
        """Return ``(retry_safe, retry_limit)``; never retry unknown/mutating work."""
        descriptor = self.get(name)
        if descriptor is None or not descriptor.read_only:
            return False, 0
        return descriptor.retry_limit > 0, descriptor.retry_limit

    def fallback_for(self, name: str) -> FallbackCandidate | None:
        """Return only fixed read-only alternatives, never a guessed action."""
        descriptor = self.get(name)
        if descriptor is None or not descriptor.read_only or not descriptor.fallback_name:
            return None
        target = self.get(descriptor.fallback_name)
        if target is None:
            return None
        return FallbackCandidate(
            name=target.name,
            arguments=dict(descriptor.fallback_arguments or {}),
            source=target.source,
        )


__all__ = ["FallbackCandidate", "ToolDescriptor", "ToolRegistry"]
