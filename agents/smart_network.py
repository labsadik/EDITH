"""Read-only local network inventory; remote control is paired-adapter-only."""
from __future__ import annotations

import ipaddress
import platform
import re
import shutil
import subprocess
from typing import Any

AGENT_ID = "smart_network"
AGENT_VERSION = "1.0.0"
_MAC = re.compile(r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _run_fixed(argv: list[str], timeout: float = 4.0) -> dict[str, Any]:
    """Execute a fixed diagnostic argv only; never accepts a model-supplied command."""
    executable = shutil.which(argv[0])
    if not executable:
        return {"available": False, "reason": f"{argv[0]} is not installed"}
    try:
        result = subprocess.run(
            [executable, *argv[1:]], capture_output=True, text=True,
            timeout=timeout, shell=False, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0),
        )
        text = (result.stdout or result.stderr or "").strip()
        return {"available": result.returncode == 0, "exit_code": result.returncode,
                "output": text[:6000]}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "diagnostic timed out"}
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__}


def _neighbors() -> tuple[list[dict[str, str]], str]:
    system = platform.system()
    candidates = ([["arp", "-a"]] if system == "Windows" else
                  [["ip", "neigh", "show"], ["arp", "-a"]])
    for argv in candidates:
        result = _run_fixed(argv)
        if not result.get("available") and not result.get("output"):
            continue
        devices = []
        seen = set()
        for line in str(result.get("output") or "").splitlines():
            ip_match, mac_match = _IPV4.search(line), _MAC.search(line)
            if not ip_match or not mac_match:
                continue
            ip = ip_match.group(0)
            try:
                address = ipaddress.ip_address(ip)
                if not (address.is_private or address.is_link_local):
                    continue
            except ValueError:
                continue
            mac = mac_match.group(0).replace("-", ":").lower()
            if (ip, mac) in seen:
                continue
            seen.add((ip, mac))
            devices.append({"ip": ip, "mac": mac, "source": "OS neighbor cache"})
        return devices[:128], argv[0]
    return [], "unavailable"


def _interfaces() -> dict[str, dict[str, Any]]:
    system = platform.system()
    if system == "Windows":
        return {
            "adapters": _run_fixed([
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-NetAdapter | Select-Object Name,Status,MacAddress,LinkSpeed,InterfaceDescription | ConvertTo-Json -Compress",
            ]),
            "wifi": _run_fixed(["netsh", "wlan", "show", "interfaces"]),
            "ip_configuration": _run_fixed([
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway,DNSServer | ConvertTo-Json -Compress",
            ]),
        }
    if system == "Darwin":
        return {
            "hardware_ports": _run_fixed(["networksetup", "-listallhardwareports"]),
            "addresses": _run_fixed(["ifconfig"]),
            "wifi": _run_fixed(["networksetup", "-getairportnetwork", "en0"]),
        }
    if system == "Linux":
        return {
            "addresses": _run_fixed(["ip", "-brief", "address"]),
            "wifi_links": _run_fixed(["iw", "dev"]),
            "connection_status": _run_fixed(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"]),
        }
    return {"interfaces": {"available": False, "reason": "unsupported platform"}}


def discover_local_devices() -> dict[str, Any]:
    """List OS-known neighbors and interface state; sends no discovery packets."""
    devices, source = _neighbors()
    return {
        "agent": AGENT_ID,
        "version": AGENT_VERSION,
        "interfaces": _interfaces(),
        "source": source,
        "devices": devices,
        "count": len(devices),
        "active_scan": False,
        "control_available": False,
        "control_note": (
            "Remote control is not enabled by discovery. A device must first complete "
            "authenticated pairing and expose a supported adapter (for example an owner-managed "
            "Home Assistant, ADB or vendor API endpoint)."
        ),
        "note": (
            "Only devices already present in the OS neighbor cache are listed. Interface details "
            "are read-only. No packets were sent to scan or control other hosts."
        ),
    }


def run_smart_network() -> str:
    import json
    return json.dumps(discover_local_devices(), ensure_ascii=False, indent=2)
