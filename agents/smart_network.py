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

AGENT_ID = "smart_network"
AGENT_VERSION = "2.0.0"
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


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


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
    response = requests.request(
        method, f"{url}/api/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload, timeout=timeout,
    )
    response.raise_for_status()
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
    if action == "status":
        _ha_request("GET", "config")
        return {"connected": True, "provider": "Home Assistant", "read_control": True, "write_control": True}
    if action == "entities":
        items = _ha_request("GET", "states")
        return {"count": len(items), "entities": [
            {"entity_id": item.get("entity_id"), "state": item.get("state"),
             "name": (item.get("attributes") or {}).get("friendly_name")}
            for item in items if isinstance(item, dict)
        ]}
    if action not in {"read", "control"}:
        raise ValueError("Use action discover, status, entities, read or control")
    if not _ENTITY.fullmatch(str(entity_id or "")):
        raise ValueError("Specify an exact Home Assistant entity_id, for example light.living_room")
    if action == "read":
        state = _ha_request("GET", f"states/{entity_id}")
        return {"entity_id": state.get("entity_id"), "state": state.get("state"),
                "attributes": state.get("attributes") or {}}

    domain, _, service_name = str(service or "").partition(".")
    if not service_name:
        raise ValueError("Specify an allowed service such as light.turn_on")
    if domain not in _ALLOWED_SERVICES or service_name not in _ALLOWED_SERVICES[domain]:
        raise ValueError("This Home Assistant service is not in EDITH's write allowlist")
    if entity_id.split(".", 1)[0] != domain:
        raise ValueError("Service domain must match the selected entity")
    data = dict(service_data or {})
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
    if "hvac_mode" in data and data["hvac_mode"] not in {"off", "heat", "cool", "auto", "heat_cool", "dry", "fan_only"}:
        raise ValueError("hvac_mode is not in EDITH's allowed mode list")
    state = _ha_request("GET", f"states/{entity_id}")
    data["entity_id"] = entity_id
    result = _ha_request("POST", f"services/{domain}/{service_name}", payload=data)
    return {"ok": True, "entity_id": entity_id, "service": f"{domain}.{service_name}", "result": result}


def run_smart_network(
    action: str = "discover", entity_id: str = "", service: str = "",
    service_data: dict | None = None, topic: str = "", payload: str = "",
) -> str:
    """Run passive inventory, paired HA operations or locally allowlisted MQTT."""
    action = str(action or "discover").strip().lower()
    if action.startswith("mqtt_"):
        from agents.mqtt_bridge import run_mqtt_action
        result = run_mqtt_action(action, topic=topic, payload=payload)
    else:
        result = discover_local_devices() if action == "discover" else _home_assistant(
            action, entity_id=entity_id, service=service, service_data=service_data
        )
    return json.dumps(result, ensure_ascii=False, indent=2)
