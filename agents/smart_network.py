"""Read local network inventory and control paired Home Assistant entities safely."""
from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from core.app_paths import config_path

AGENT_ID = "smart_network"
AGENT_VERSION = "2.1.0"
_MAC = re.compile(r"(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_ENTITY = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
_ALLOWED_SERVICES = {
    "light": {"turn_on", "turn_off", "toggle"},
    "switch": {"turn_on", "turn_off", "toggle"},
    "input_boolean": {"turn_on", "turn_off", "toggle"},
    "climate": {"set_temperature", "set_hvac_mode"},
    "cover": {"open_cover", "close_cover", "set_cover_position"},
    "scene": {"turn_on"},
}
_ALLOWED_SERVICE_DATA = {
    "brightness", "brightness_pct", "color_temp_kelvin", "color_temp",
    "transition", "temperature", "hvac_mode", "position", "tilt_position",
}


def _run_fixed(argv: list[str], timeout: float = 4.0) -> dict[str, Any]:
    """Run fixed diagnostic argv only; never accepts a model-supplied command."""
    executable = shutil.which(argv[0])
    if not executable:
        return {"available": False, "reason": f"{argv[0]} is not installed"}
    try:
        result = subprocess.run(
            [executable, *argv[1:]], capture_output=True, text=True,
            timeout=timeout, shell=False, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0),
        )
        output = (result.stdout or result.stderr or "").strip()
        return {"available": result.returncode == 0, "exit_code": result.returncode,
                "output": output[:6000]}
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
        devices, seen = [], set()
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
            if (ip, mac) not in seen:
                seen.add((ip, mac))
                devices.append({"ip": ip, "mac": mac, "source": "OS neighbor cache"})
        return devices[:128], argv[0]
    return [], "unavailable"


def _interfaces() -> dict[str, dict[str, Any]]:
    system = platform.system()
    if system == "Windows":
        return {
            "adapters": _run_fixed(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-NetAdapter | Select-Object Name,Status,MacAddress,LinkSpeed,InterfaceDescription | ConvertTo-Json -Compress"]),
            "wifi": _run_fixed(["netsh", "wlan", "show", "interfaces"]),
            "ip_configuration": _run_fixed(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway,DNSServer | ConvertTo-Json -Compress"]),
        }
    if system == "Darwin":
        return {"hardware_ports": _run_fixed(["networksetup", "-listallhardwareports"]),
                "addresses": _run_fixed(["ifconfig"]),
                "wifi": _run_fixed(["networksetup", "-getairportnetwork", "en0"])}
    if system == "Linux":
        return {"addresses": _run_fixed(["ip", "-brief", "address"]),
                "wifi_links": _run_fixed(["iw", "dev"]),
                "connection_status": _run_fixed(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"])}
    return {"interfaces": {"available": False, "reason": "unsupported platform"}}



def _parse_windows_wifi_networks(output: str, interface: str) -> list[dict[str, Any]]:
    """Parse netsh's SSID/BSSID blocks without assuming one AP per SSID."""
    matches = list(re.finditer(
        r"(?im)^\s*SSID\s+\d+\s*:\s*(.*?)\s*$", output
    ))
    networks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(output)
        block = output[match.end():end]
        ssid = match.group(1).strip() or "(hidden network)"

        def field(label: str, text: str) -> str:
            found = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", text)
            return found.group(1).strip() if found else ""

        bssids = list(re.finditer(r"(?im)^\s*BSSID\s+\d+\s*:\s*([0-9a-f:.-]+)\s*$", block))
        if not bssids:
            networks.append({
                "ssid": ssid, "bssid": None, "interface": interface,
                "authentication": field("Authentication", block),
                "encryption": field("Encryption", block),
                "signal_percent": None, "channel": None, "radio_type": "",
            })
            continue
        for b_index, bssid in enumerate(bssids):
            b_end = bssids[b_index + 1].start() if b_index + 1 < len(bssids) else len(block)
            details = block[bssid.end():b_end]
            signal = field("Signal", details).rstrip("%")
            channel = field("Channel", details)
            try:
                signal_value = max(0, min(100, int(signal)))
            except (TypeError, ValueError):
                signal_value = None
            try:
                channel_value = int(channel)
            except (TypeError, ValueError):
                channel_value = None
            networks.append({
                "ssid": ssid, "bssid": bssid.group(1).lower(),
                "interface": interface,
                "authentication": field("Authentication", block),
                "encryption": field("Encryption", block),
                "signal_percent": signal_value, "channel": channel_value,
                "radio_type": field("Radio type", details),
            })
    return networks[:256]


def _split_nmcli_fields(line: str) -> list[str]:
    """Split nmcli's terse colon fields while respecting escaped colons."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def _parse_nmcli_wifi_networks(output: str) -> list[dict[str, Any]]:
    networks: list[dict[str, Any]] = []
    for line in output.splitlines():
        fields = _split_nmcli_fields(line)
        if len(fields) < 8:
            continue
        in_use, ssid, bssid, channel, frequency, rate, signal, security = fields[:8]
        try:
            signal_value = max(0, min(100, int(signal)))
        except (TypeError, ValueError):
            signal_value = None
        try:
            channel_value = int(channel)
        except (TypeError, ValueError):
            channel_value = None
        networks.append({
            "ssid": ssid or "(hidden network)", "bssid": bssid.lower() or None,
            "interface": "NetworkManager", "in_use": in_use == "*",
            "channel": channel_value, "frequency": frequency or None,
            "rate": rate or None, "signal_percent": signal_value,
            "security": security or "Open",
        })
    return networks[:256]


def _parse_macos_wifi_networks(output: str, interface: str) -> list[dict[str, Any]]:
    """Parse the tabular output of Apple's airport -s scan command."""
    networks: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^(.*?)\s+([0-9a-f]{2}(?::[0-9a-f]{2}){5})\s+(-?\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$",
        re.IGNORECASE,
    )
    for line in output.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        ssid, bssid, rssi, channel, _ht, _cc, security = match.groups()
        try:
            rssi_value = int(rssi)
        except ValueError:
            rssi_value = None
        networks.append({
            "ssid": ssid.strip() or "(hidden network)", "bssid": bssid.lower(),
            "interface": interface, "rssi_dbm": rssi_value,
            "channel": channel, "security": security.strip() or "Unknown",
        })
    return networks[:256]


def scan_wifi_networks() -> dict[str, Any]:
    """Scan nearby Wi-Fi SSIDs via the OS WLAN service; never probe LAN hosts."""
    system = platform.system()
    adapters: list[dict[str, Any]] = []
    networks: list[dict[str, Any]] = []

    if system == "Windows":
        interfaces = _run_fixed(["netsh", "wlan", "show", "interfaces"], timeout=5.0)
        if not interfaces.get("available"):
            return {
                "ok": False, "platform": system, "adapters": [], "networks": [],
                "count": 0, "error": interfaces.get("reason") or interfaces.get("output")
                         or "Windows WLAN service or netsh is unavailable.",
            }
        names = re.findall(r"(?im)^\s*Name\s*:\s*(.*?)\s*$",
                           str(interfaces.get("output") or ""))
        names = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        if not names:
            return {
                "ok": False, "platform": system, "adapters": [], "networks": [],
                "count": 0,
                "error": "No WLAN interface is exposed by Windows. Check that the USB Wi-Fi dongle driver is installed and the WLAN AutoConfig service is running.",
            }
        for name in names[:8]:
            scan = _run_fixed(
                ["netsh", "wlan", "show", "networks", "mode=bssid", "interface=" + name],
                timeout=8.0,
            )
            rows = _parse_windows_wifi_networks(str(scan.get("output") or ""), name)
            adapters.append({
                "name": name, "available": bool(scan.get("available")),
                "network_count": len(rows),
                "error": scan.get("reason") if not scan.get("available") else None,
            })
            networks.extend(rows)
        ok = any(item["available"] for item in adapters)
        return {
            "ok": ok, "platform": system, "adapters": adapters,
            "networks": networks[:256], "count": len(networks[:256]),
            "error": None if ok else "Windows could not scan any WLAN adapter. Check WLAN AutoConfig and the adapter driver.",
            "note": "Networks are read from each OS WLAN interface; no connection is made and no credentials are collected.",
        }

    if system == "Linux":
        scan = _run_fixed([
            "nmcli", "-t", "-f",
            "IN-USE,SSID,BSSID,CHAN,FREQ,RATE,SIGNAL,SECURITY",
            "device", "wifi", "list", "--rescan", "yes",
        ], timeout=10.0)
        if not scan.get("available"):
            return {
                "ok": False, "platform": system, "adapters": [], "networks": [],
                "count": 0,
                "error": scan.get("reason") or scan.get("output")
                         or "NetworkManager nmcli is unavailable. Install/enable NetworkManager or provide an OS-supported Wi-Fi scan tool.",
            }
        networks = _parse_nmcli_wifi_networks(str(scan.get("output") or ""))
        return {
            "ok": True, "platform": system,
            "adapters": [{"name": "NetworkManager Wi-Fi", "available": True,
                          "network_count": len(networks)}],
            "networks": networks, "count": len(networks),
            "note": "NetworkManager refreshed visible Wi-Fi networks; no network was joined.",
        }

    if system == "Darwin":
        airport = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        scan = _run_fixed([airport, "-s"], timeout=10.0)
        if not scan.get("available"):
            return {
                "ok": False, "platform": system, "adapters": [], "networks": [],
                "count": 0,
                "error": scan.get("reason") or scan.get("output")
                         or "Apple's airport scan utility is unavailable on this macOS version.",
            }
        networks = _parse_macos_wifi_networks(str(scan.get("output") or ""), "airport")
        return {
            "ok": True, "platform": system,
            "adapters": [{"name": "airport", "available": True,
                          "network_count": len(networks)}],
            "networks": networks, "count": len(networks),
            "note": "Visible Wi-Fi beacons only; no network was joined.",
        }

    return {
        "ok": False, "platform": system, "adapters": [], "networks": [],
        "count": 0, "error": "Wi-Fi scanning is not implemented for this operating system.",
    }


def _config_path() -> Path:
    return config_path()


def _ha_credentials(required: bool = True) -> tuple[str, str] | None:
    from core.secrets import get_config_secret
    path = _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        data = {}
    url = str(os.environ.get("EDITH_HOME_ASSISTANT_URL") or data.get("home_assistant_url") or "").strip().rstrip("/")
    token = str(os.environ.get("EDITH_HOME_ASSISTANT_TOKEN") or
                (get_config_secret("home_assistant_token", path).value or ""))
    if not url or not token:
        if required:
            raise RuntimeError(
                "Home Assistant is not paired. Run scripts/configure_home_assistant.py locally "
                "or set EDITH_HOME_ASSISTANT_URL and EDITH_HOME_ASSISTANT_TOKEN."
            )
        return None
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        raise RuntimeError("Configured Home Assistant URL must be plain http(s), without embedded credentials")
    if parts.query or parts.fragment:
        raise RuntimeError("Home Assistant URL must not contain a query string or fragment")
    return url, token



def test_home_assistant_connection(url: str, token: str, timeout: float = 5.0) -> dict[str, Any]:
    """Verify owner-provided credentials against the HA API before saving them."""
    clean = str(url or "").strip().rstrip("/")
    secret = str(token or "").strip()
    parts = urlsplit(clean)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        raise ValueError("Home Assistant URL must be a plain http(s) URL without embedded credentials")
    if parts.query or parts.fragment or not secret:
        raise ValueError("A clean Home Assistant URL and long-lived access token are required")
    try:
        response = requests.get(
            f"{clean}/api/config",
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
            timeout=max(1.0, min(float(timeout), 10.0)),
            allow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            raise RuntimeError("Home Assistant redirected the API request. Use the final local HTTPS/HTTP URL directly.")
        if response.status_code in {401, 403}:
            raise RuntimeError("Home Assistant rejected this token. Create a new long-lived access token and retry.")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Home Assistant returned an invalid API configuration response.")
    except requests.Timeout as exc:
        raise RuntimeError("Home Assistant connection test timed out. Check the host and local network.") from exc
    except requests.ConnectionError as exc:
        raise RuntimeError("Home Assistant is unreachable at this URL. Check its host, port and network.") from exc
    except requests.HTTPError as exc:
        raise RuntimeError(f"Home Assistant API returned HTTP {getattr(exc.response, 'status_code', 'error')}.") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Home Assistant connection test failed: {type(exc).__name__}.") from exc
    except ValueError as exc:
        if "JSON" in str(exc):
            raise RuntimeError("Home Assistant did not return valid JSON from /api/config.") from exc
        raise
    return {"ok": True, "connected": True, "provider": "Home Assistant",
            "message": "Home Assistant credentials verified; ready to pair."}


def configure_home_assistant(url: str, token: str) -> dict[str, Any]:
    """Store the HA URL locally and bearer token in the OS keychain."""
    from core.secrets import save_config_secret
    path = _config_path()
    clean = str(url or "").strip().rstrip("/")
    parts = urlsplit(clean)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
        raise ValueError("Home Assistant URL must be a plain http(s) URL without embedded credentials")
    if parts.query or parts.fragment or not str(token or "").strip():
        raise ValueError("A clean Home Assistant URL and long-lived access token are required")
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("EDITH config must be a JSON object")
    data["home_assistant_url"] = clean
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    status = save_config_secret("home_assistant_token", str(token).strip(), path)
    return {"saved": True, "url": clean,
            "token_storage": getattr(status, "storage", "OS keychain")}


def _ha_request(method: str, path: str, *, payload: dict | None = None, timeout: float = 12.0):
    credentials = _ha_credentials()
    assert credentials is not None
    url, token = credentials
    try:
        response = requests.request(
            method, f"{url}/api/{path.lstrip('/')}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload, timeout=timeout,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise RuntimeError("Home Assistant request timed out. Check that the local Home Assistant host is online.") from exc
    except requests.ConnectionError as exc:
        raise RuntimeError("Home Assistant is paired but unreachable. Check the URL, network and Home Assistant service.") from exc
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "unknown")
        if status in {401, 403}:
            raise RuntimeError("Home Assistant rejected the saved token. Create a new long-lived access token and pair again.") from exc
        raise RuntimeError(f"Home Assistant API returned HTTP {status}. Check the integration and entity permissions.") from exc
    if not response.content:
        return {}
    return response.json()


def discover_local_devices() -> dict[str, Any]:
    devices, source = _neighbors()
    try:
        ha_configured = _ha_credentials(required=False) is not None
    except Exception:
        ha_configured = False
    return {
        "agent": AGENT_ID, "version": AGENT_VERSION, "interfaces": _interfaces(),
        "source": source, "devices": devices, "count": len(devices),
        "active_scan": False, "home_assistant_paired": ha_configured,
        "control_available": ha_configured,
        "control_note": "authenticated pairing with the user's Home Assistant account is required for read/write control; every write requires local confirmation.",
        "note": "Only OS-known neighbors are listed. No packets are sent to scan other hosts.",
    }


def _home_assistant(action: str, entity_id: str = "", service: str = "",
                    service_data: dict | None = None) -> dict[str, Any]:
    """Validate requested operations before checking pairing or making network calls."""
    action = str(action or "").strip().lower()
    if action not in {"status", "entities", "read", "control"}:
        raise ValueError("Use action discover, status, entities, read or control")

    domain = service_name = ""
    data = dict(service_data or {})
    if action in {"read", "control"}:
        if not _ENTITY.fullmatch(str(entity_id or "")):
            raise ValueError("Specify an exact Home Assistant entity_id, for example light.living_room")

    if action == "control":
        domain, separator, service_name = str(service or "").partition(".")
        if not separator or not service_name:
            raise ValueError("Specify an allowed service such as light.turn_on")
        if domain not in _ALLOWED_SERVICES or service_name not in _ALLOWED_SERVICES[domain]:
            raise ValueError("This Home Assistant service is not in EDITH's write allowlist")
        if entity_id.split(".", 1)[0] != domain:
            raise ValueError("Service domain must match the selected entity")
        unexpected = set(data) - _ALLOWED_SERVICE_DATA
        if unexpected:
            raise ValueError("Unsupported service_data fields: " + ", ".join(sorted(unexpected)))
        ranges = {
            "brightness": (0, 255),
            "brightness_pct": (0, 100),
            "color_temp": (1, 500),
            "color_temp_kelvin": (1000, 12000),
            "position": (0, 100),
            "tilt_position": (0, 100),
            "transition": (0, 3600),
        }
        for key, (minimum, maximum) in ranges.items():
            if key in data:
                value = data[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
                    raise ValueError(f"{key} must be numeric between {minimum} and {maximum}")
        if "temperature" in data:
            try:
                temperature = float(data["temperature"])
            except (TypeError, ValueError) as exc:
                raise ValueError("temperature must be numeric") from exc
            if not 5 <= temperature <= 35:
                raise ValueError("temperature must be between 5 and 35 C")
            data["temperature"] = temperature
        if "hvac_mode" in data and data["hvac_mode"] not in {
            "off", "heat", "cool", "auto", "heat_cool", "dry", "fan_only"
        }:
            raise ValueError("hvac_mode is not in EDITH's allowed mode list")

    # All validation is complete. Only then resolve credentials / pairing.
    try:
        credentials = _ha_credentials(required=False)
    except (RuntimeError, OSError, ValueError) as exc:
        return {
            "ok": False, "connected": False, "paired": False,
            "needs_pairing": True, "provider": "Home Assistant",
            "error": str(exc),
            "setup": "Open EDITH Controls → Smart Network → Pair Home Assistant, or set "
                     "EDITH_HOME_ASSISTANT_URL and EDITH_HOME_ASSISTANT_TOKEN.",
        }
    if not credentials:
        return {
            "ok": False, "connected": False, "paired": False,
            "needs_pairing": True, "provider": "Home Assistant",
            "action": action,
            "message": "Home Assistant is not paired. Local network discovery remains available; "
                       "smart-home entity reads and controls are disabled until pairing is completed.",
            "setup": "Run scripts/configure_home_assistant.py locally, or set "
                     "EDITH_HOME_ASSISTANT_URL and EDITH_HOME_ASSISTANT_TOKEN. "
                     "The token is stored in the OS keychain when available.",
        }

    if action == "status":
        _ha_request("GET", "config")
        return {"ok": True, "connected": True, "provider": "Home Assistant",
                "read_control": True, "write_control": True}
    if action == "entities":
        items = _ha_request("GET", "states")
        return {"ok": True, "count": len(items), "entities": [
            {"entity_id": item.get("entity_id"), "state": item.get("state"),
             "name": (item.get("attributes") or {}).get("friendly_name")}
            for item in items if isinstance(item, dict)
        ]}
    if action == "read":
        state = _ha_request("GET", f"states/{entity_id}")
        return {"ok": True, "entity_id": state.get("entity_id"),
                "state": state.get("state"), "attributes": state.get("attributes") or {}}

    # Re-read the entity immediately before write to confirm it still exists and
    # its domain matches; local confirmation is enforced by the outer dispatcher.
    state = _ha_request("GET", f"states/{entity_id}")
    if not isinstance(state, dict) or state.get("entity_id") != entity_id:
        raise RuntimeError("Home Assistant did not return the selected entity")
    data["entity_id"] = entity_id
    result = _ha_request("POST", f"services/{domain}/{service_name}", payload=data)
    return {"ok": True, "entity_id": entity_id, "service": f"{domain}.{service_name}",
            "result": result}


def run_smart_network(
    action: str = "discover", entity_id: str = "", service: str = "",
    service_data: dict | None = None, topic: str = "", payload: str = "",
) -> str:
    """Run local Wi-Fi scanning, inventory, paired HA operations or allowlisted MQTT."""
    action = str(action or "discover").strip().lower()
    if action.startswith("mqtt_"):
        from agents.mqtt_bridge import run_mqtt_action
        result = run_mqtt_action(action, topic=topic, payload=payload)
    elif action == "discover":
        result = discover_local_devices()
    elif action == "wifi_scan":
        result = scan_wifi_networks()
    else:
        try:
            result = _home_assistant(
                action, entity_id=entity_id, service=service, service_data=service_data
            )
        except (RuntimeError, requests.RequestException) as exc:
            result = {
                "ok": False, "connected": False, "paired": True,
                "provider": "Home Assistant",
                "error": str(exc),
                "setup": "Check the paired Home Assistant URL/token and retry. "
                         "No smart-home command was confirmed as successful.",
            }
    return json.dumps(result, ensure_ascii=False, indent=2)
