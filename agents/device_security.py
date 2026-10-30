"""Read-only local device security posture checks for EDITH."""
from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

AGENT_ID = "device_security"
AGENT_VERSION = "1.0.0"


def _read_command(argv: list[str], timeout: float = 5.0) -> dict[str, Any]:
    """Run one fixed, read-only OS diagnostic command; never accept model argv."""
    executable = shutil.which(argv[0])
    if not executable:
        return {"available": False, "reason": f"{argv[0]} is not installed"}
    try:
        completed = subprocess.run(
            [executable, *argv[1:]], capture_output=True, text=True,
            timeout=timeout, check=False, shell=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0),
        )
        output = (completed.stdout or completed.stderr or "").strip()
        return {"available": completed.returncode == 0, "exit_code": completed.returncode,
                "output": output[:5000]}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "diagnostic timed out"}
    except Exception as exc:
        return {"available": False, "reason": type(exc).__name__}


def security_posture() -> dict[str, Any]:
    """Report observable security controls without changing OS configuration."""
    system = platform.system()
    checks: dict[str, Any] = {}
    if system == "Windows":
        checks["firewall"] = _read_command([
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-NetFirewallProfile | Select-Object Name,Enabled | ConvertTo-Json -Compress",
        ])
        checks["defender"] = _read_command([
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "Get-MpComputerStatus | Select-Object AntivirusEnabled,RealTimeProtectionEnabled,AntispywareEnabled | ConvertTo-Json -Compress",
        ])
    elif system == "Darwin":
        checks["application_firewall"] = _read_command(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"])
        checks["gatekeeper"] = _read_command(["spctl", "--status"])
        checks["system_integrity_protection"] = _read_command(["csrutil", "status"])
    elif system == "Linux":
        checks["ufw"] = _read_command(["ufw", "status"])
        checks["firewalld"] = _read_command(["firewall-cmd", "--state"])
        checks["apparmor"] = _read_command(["aa-status", "--enabled"])
        checks["selinux"] = _read_command(["getenforce"])
    else:
        checks["platform_security"] = {"available": False, "reason": "unsupported platform"}
    available = [name for name, item in checks.items() if item.get("available")]
    return {
        "agent": AGENT_ID, "version": AGENT_VERSION, "platform": system,
        "mode": "read-only audit", "checks": checks,
        "checks_available": available,
        "note": "Unavailable checks are reported as unknown, not assumed secure or insecure. No settings were changed.",
    }


def run_security_audit(device_service=None) -> str:
    """Combine fixed OS security queries with EDITH's bounded hardware inventory."""
    result = security_posture()
    if device_service is not None:
        for operation in ("capabilities", "hardware_inventory", "network_info"):
            try:
                receipt = device_service.execute({"operation": operation, "arguments": {}})
                result[operation] = receipt.get("data") if receipt.get("ok") else {
                    "available": False, "error": receipt.get("error") or "unavailable"
                }
            except Exception as exc:
                result[operation] = {"available": False, "error": type(exc).__name__}
    import json
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)[:16000]
