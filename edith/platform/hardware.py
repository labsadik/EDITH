"""Cross-platform local hardware discovery with stable, non-sensitive fields."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
from typing import Any, Callable

import psutil


def _safe(call, default=None):
    try:
        return call()
    except Exception:
        return default


def _record(value):
    return value._asdict() if hasattr(value, "_asdict") else value


def _command(read_command: Callable | None, argv: list[str], *, timeout: int = 4) -> str | None:
    if read_command is None:
        return None
    return _safe(lambda: read_command(argv, timeout=timeout))


def _audio_devices() -> list[dict[str, Any]]:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception:
        return []
    return [
        {
            "name": str(device.get("name") or "Unknown"),
            "inputs": int(device.get("max_input_channels") or 0),
            "outputs": int(device.get("max_output_channels") or 0),
            "default_sample_rate": device.get("default_samplerate"),
        }
        for device in devices[:80]
    ]


def _linux_displays() -> list[dict[str, Any]]:
    displays = []
    for connector in sorted(Path("/sys/class/drm").glob("*/status")):
        status = _safe(lambda: connector.read_text().strip())
        if status != "connected":
            continue
        name = connector.parent.name
        modes = connector.parent / "modes"
        displays.append({
            "name": name,
            "connected": True,
            "modes": (_safe(lambda: modes.read_text().splitlines(), []) or [])[:20],
        })
    return displays


def _system_profiler(read_command: Callable | None, section: str) -> list[dict[str, Any]]:
    raw = _command(read_command, ["system_profiler", section, "-json"], timeout=8)
    if not raw:
        return []
    data = _safe(lambda: json.loads(raw), {}) or {}
    value = data.get(section) or []
    return value if isinstance(value, list) else []


def _windows_cim(read_command: Callable | None, class_name: str, properties: str) -> list[dict[str, Any]]:
    script = (
        f"Get-CimInstance {class_name} | Select-Object {properties} | "
        "ConvertTo-Json -Compress"
    )
    raw = _command(read_command, ["powershell", "-NoProfile", "-Command", script], timeout=8)
    if not raw:
        return []
    value = _safe(lambda: json.loads(raw), [])
    if isinstance(value, dict):
        value = [value]
    return value if isinstance(value, list) else []


def collect_hardware_inventory(
    system: str | None = None,
    read_command: Callable | None = None,
) -> dict[str, Any]:
    """Return a bounded inventory; absent probes become empty/N/A, never an exception."""
    system = system or platform.system()
    memory = _safe(psutil.virtual_memory)
    battery = _safe(psutil.sensors_battery)
    inventory: dict[str, Any] = {
        "system": system,
        "architecture": platform.machine() or None,
        "cpu": {
            "name": platform.processor() or None,
            "physical_cores": _safe(lambda: psutil.cpu_count(logical=False)),
            "logical_cores": _safe(lambda: psutil.cpu_count(logical=True)),
            "frequency": _record(_safe(psutil.cpu_freq)),
        },
        "memory": {
            "total_bytes": getattr(memory, "total", None),
            "available_bytes": getattr(memory, "available", None),
        },
        "storage": [],
        "network_adapters": [],
        "displays": [],
        "audio_devices": _audio_devices(),
        "usb": [],
        "graphics": [],
        "battery": _record(battery),
    }
    for partition in _safe(lambda: psutil.disk_partitions(all=False), []) or []:
        usage = _safe(lambda p=partition.mountpoint: psutil.disk_usage(p))
        inventory["storage"].append({
            "mount": partition.mountpoint,
            "filesystem": partition.fstype or None,
            "total_bytes": getattr(usage, "total", None),
            "free_bytes": getattr(usage, "free", None),
        })
    stats = _safe(psutil.net_if_stats, {}) or {}
    for name, addresses in (_safe(psutil.net_if_addrs, {}) or {}).items():
        state = stats.get(name)
        inventory["network_adapters"].append({
            "name": name,
            "up": getattr(state, "isup", None),
            "link_speed_mbps": getattr(state, "speed", None),
            "addresses": [
                item.address for item in addresses
                if getattr(item.family, "name", "") in {"AF_INET", "AF_INET6"}
            ],
        })

    if system == "Windows":
        inventory["displays"] = _windows_cim(read_command, "Win32_DesktopMonitor", "Name,ScreenWidth,ScreenHeight,Status")
        inventory["graphics"] = _windows_cim(read_command, "Win32_VideoController", "Name,AdapterRAM,CurrentHorizontalResolution,CurrentVerticalResolution")
        inventory["usb"] = _windows_cim(read_command, "Win32_USBHub", "Name,Status")
    elif system == "Darwin":
        inventory["graphics"] = _system_profiler(read_command, "SPDisplaysDataType")
        inventory["usb"] = _system_profiler(read_command, "SPUSBDataType")
        displays = []
        for gpu in inventory["graphics"]:
            for display in gpu.get("spdisplays_ndrvs", []) or []:
                displays.append({
                    "name": display.get("_name") or display.get("spdisplays_display-product-name"),
                    "resolution": display.get("spdisplays_resolution"),
                    "connected": True,
                })
        inventory["displays"] = displays
    elif system == "Linux":
        inventory["displays"] = _linux_displays()
        lspci = _command(read_command, ["lspci"])
        if lspci:
            inventory["graphics"] = [
                {"name": line} for line in lspci.splitlines()
                if any(token in line.lower() for token in ("vga", "3d controller", "display controller"))
            ][:20]
        if shutil.which("lsusb"):
            usb = _command(read_command, ["lsusb"])
            inventory["usb"] = [{"name": line} for line in (usb or "").splitlines()[:80]]
    return inventory


__all__ = ["collect_hardware_inventory"]
