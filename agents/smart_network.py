"""Read-only local network inventory; no probing, exploitation or device takeover."""
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


def _neighbors() -> tuple[list[dict[str, str]], str]:
    system = platform.system()
    candidates = ([ ["arp", "-a"] ] if system == "Windows" else
                  [["ip", "neigh", "show"], ["arp", "-a"]])
    for argv in candidates:
        executable = shutil.which(argv[0])
        if not executable:
            continue
        try:
            result = subprocess.run(
                [executable, *argv[1:]], capture_output=True, text=True,
                timeout=4, shell=False, check=False,
                creationflags=(subprocess.CREATE_NO_WINDOW if system == "Windows" else 0),
            )
            if result.returncode != 0 and not result.stdout:
                continue
            devices = []
            seen = set()
            for line in (result.stdout or "").splitlines():
                ip_match, mac_match = _IPV4.search(line), _MAC.search(line)
                if not ip_match or not mac_match:
                    continue
                ip = ip_match.group(0)
                try:
                    if not ipaddress.ip_address(ip).is_private:
                        continue
                except ValueError:
                    continue
                mac = mac_match.group(0).replace("-", ":").lower()
                if (ip, mac) in seen:
                    continue
                seen.add((ip, mac))
                devices.append({"ip": ip, "mac": mac, "source": "OS neighbor cache"})
            return devices[:128], argv[0]
        except Exception:
            continue
    return [], "unavailable"


def discover_local_devices() -> dict[str, Any]:
    """List known local neighbors; this does not actively scan or control devices."""
    devices, source = _neighbors()
    return {
        "agent": AGENT_ID, "version": AGENT_VERSION,
        "source": source, "devices": devices,
        "count": len(devices), "active_scan": False,
        "control_available": False,
        "control_note": "Remote control is disabled until a device exposes a trusted adapter and completes authenticated pairing.",
        "note": "Only devices already present in the OS neighbor cache are listed. No packets were sent to discover hosts.",
    }


def run_smart_network() -> str:
    import json
    return json.dumps(discover_local_devices(), ensure_ascii=False, indent=2)
