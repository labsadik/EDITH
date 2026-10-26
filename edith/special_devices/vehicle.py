"""Vehicle integration boundary: simulation by default, OEM control by adapter.

EDITH never discovers, connects to, or controls a real vehicle merely because it
is installed on a device.  A manufacturer-specific integration must be supplied
by the owner, authenticate through the OEM flow, and explicitly report its
authorised state.  This module keeps the reusable runtime contract testable
without pretending that a generic desktop app can drive a car.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


def device_result(
    ok: bool = True, data: Any = None, error: str | None = None, unsupported: bool = False
) -> dict[str, Any]:
    """Match the platform layer's structured-result contract."""
    return {"ok": bool(ok), "data": data, "error": error, "unsupported": bool(unsupported)}


class VehicleAdapter(ABC):
    """Minimal common contract for a simulator or owner-installed OEM adapter."""

    adapter_id = "vehicle"
    display_name = "Vehicle"
    simulator = False

    @abstractmethod
    def capabilities(self) -> dict[str, Any]:
        """Describe the adapter without claiming hardware is attached."""

    @abstractmethod
    def invoke(self, operation: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return `{ok, data, error, unsupported}` for every operation."""


@dataclass
class VehicleSimulatorAdapter(VehicleAdapter):
    """Deterministic in-memory simulator for UI/runtime integration tests."""

    adapter_id: str = "vehicle_simulator"
    display_name: str = "Vehicle simulator"
    simulator: bool = True
    _ignition: bool = False
    _gear: str = "park"
    _speed_kph: float = 0.0
    _battery_percent: float = 80.0

    def capabilities(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "simulator": True,
            "operations": ["status", "simulate_ignition", "simulate_drive", "simulate_stop"],
            "note": "Simulation only. No physical vehicle connection is attempted.",
        }

    def _status(self) -> dict[str, Any]:
        return {
            "mode": "simulation",
            "ignition": self._ignition,
            "gear": self._gear,
            "speed_kph": self._speed_kph,
            "battery_percent": self._battery_percent,
        }

    def invoke(self, operation: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        operation = str(operation or "").strip().lower()
        args = dict(arguments or {})
        if operation == "status":
            return device_result(data=self._status())
        if operation == "simulate_ignition":
            enabled = args.get("enabled")
            if not isinstance(enabled, bool):
                return device_result(False, error="simulate_ignition requires boolean enabled.")
            self._ignition = enabled
            if not enabled:
                self._gear, self._speed_kph = "park", 0.0
            return device_result(data=self._status())
        if operation == "simulate_drive":
            if not self._ignition:
                return device_result(False, error="Simulation ignition is off; no simulated drive started.")
            try:
                speed = float(args.get("speed_kph"))
            except (TypeError, ValueError):
                return device_result(False, error="simulate_drive requires numeric speed_kph from 0 through 130.")
            if not 0 <= speed <= 130:
                return device_result(False, error="Simulated speed_kph must be between 0 and 130.")
            self._speed_kph = speed
            self._gear = "drive" if speed else "park"
            self._battery_percent = max(0.0, round(self._battery_percent - speed / 10_000, 3))
            return device_result(data=self._status())
        if operation == "simulate_stop":
            self._speed_kph, self._gear = 0.0, "park"
            return device_result(data=self._status())
        return device_result(
            False,
            error=f"Unsupported vehicle simulator operation: {operation or 'empty'}.",
            unsupported=True,
        )


class AuthorizedOEMVehicleAdapter(VehicleAdapter):
    """Base class for an owner-installed, OEM-specific transport adapter.

    It deliberately exposes no default driving implementation.  A concrete
    adapter must implement a documented OEM API and manage consent/auth itself.
    """

    simulator = False

    def __init__(self, adapter_id: str, display_name: str, *, authorised: bool = False):
        self.adapter_id = str(adapter_id)
        self.display_name = str(display_name)
        self.authorised = bool(authorised)

    def capabilities(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "simulator": False,
            "authorised": self.authorised,
            "operations": ["status"],
            "note": "OEM transport is not implemented by the base adapter.",
        }

    def invoke(self, operation: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        del arguments
        if str(operation or "").strip().lower() == "status":
            return device_result(data=self.capabilities())
        return device_result(
            False,
            error=("No authorised OEM implementation is installed for this adapter; "
                   "no physical vehicle command was sent."),
            unsupported=True,
        )


class VehicleAdapterRegistry:
    """Explicit registry; registration is owner/application controlled, not model-controlled."""

    def __init__(self, adapters: list[VehicleAdapter] | None = None):
        self._adapters: dict[str, VehicleAdapter] = {}
        for adapter in adapters or [VehicleSimulatorAdapter()]:
            self.register(adapter)

    def register(self, adapter: VehicleAdapter) -> None:
        adapter_id = str(getattr(adapter, "adapter_id", "")).strip()
        if not adapter_id:
            raise ValueError("Vehicle adapter requires a non-empty adapter_id.")
        if adapter_id in self._adapters:
            raise ValueError(f"Vehicle adapter already registered: {adapter_id}")
        self._adapters[adapter_id] = adapter

    def list_capabilities(self) -> list[dict[str, Any]]:
        return [adapter.capabilities() for adapter in self._adapters.values()]

    def invoke(
        self, adapter_id: str, operation: str, arguments: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        adapter = self._adapters.get(str(adapter_id or ""))
        if adapter is None:
            return device_result(
                False,
                error=f"Unknown vehicle adapter: {adapter_id or 'empty'}.",
                unsupported=True,
            )
        try:
            response = adapter.invoke(operation, arguments)
            if not isinstance(response, dict) or set(response) != {"ok", "data", "error", "unsupported"}:
                return device_result(False, error="Vehicle adapter returned an invalid result.")
            return response
        except Exception as exc:
            return device_result(False, error=f"Vehicle adapter error: {type(exc).__name__}: {exc}")


__all__ = [
    "AuthorizedOEMVehicleAdapter",
    "VehicleAdapter",
    "VehicleAdapterRegistry",
    "VehicleSimulatorAdapter",
    "device_result",
]
