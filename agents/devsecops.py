"""Offline static DevSecOps checks for locally generated EDITH projects."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any

AGENT_ID = "devsecops_security"
AGENT_VERSION = "1.0.0"
_RULES = [
    ("critical", "hardcoded-credential", re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"][A-Za-z0-9_./+=-]{16,}['\"]"
    ), "Possible hard-coded credential; move it to local secret storage."),
    ("critical", "private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
     "Private key material must not be committed into project source."),
    ("high", "dynamic-code", re.compile(r"\b(?:eval|exec)\s*\("),
     "Dynamic code execution increases injection risk; remove or tightly constrain it."),
    ("high", "unsafe-deserialization", re.compile(r"\bpickle\.(?:load|loads)\s*\("),
     "Untrusted pickle input can execute code; prefer a non-executable data format."),
    ("high", "unsafe-shell", re.compile(r"subprocess\.[A-Za-z_]+\([^\n]*\bshell\s*=\s*True"),
     "Shell execution should use exact argument arrays where possible."),
    ("medium", "tls-verification-disabled", re.compile(r"\bverify\s*=\s*False\b"),
     "TLS certificate validation is disabled."),
    ("medium", "unsafe-yaml-loader", re.compile(r"\byaml\.load\s*\("),
     "Use yaml.safe_load for untrusted YAML input."),
]

def scan_project(project_dir: str | Path, max_files: int = 300) -> dict[str, Any]:
    root = Path(project_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Project directory does not exist.")
    findings, inspected = [], 0
    ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "target", "dist"}
    for path in root.rglob("*"):
        try:
            if any(part in ignored for part in path.relative_to(root).parts):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in {
                ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
                ".php", ".rb", ".sh", ".ps1", ".json", ".yaml", ".yml", ".toml",
            }:
                continue
            inspected += 1
            if inspected > max_files:
                break
            if path.stat().st_size > 1_000_000:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line_number, line in enumerate(content.splitlines(), start=1):
                for severity, rule_id, pattern, recommendation in _RULES:
                    if pattern.search(line):
                        findings.append({
                            "severity": severity, "rule": rule_id,
                            "file": path.relative_to(root).as_posix(),
                            "line": line_number, "recommendation": recommendation,
                        })
        except (OSError, ValueError):
            continue
    counts = {level: sum(1 for finding in findings if finding["severity"] == level)
              for level in ("critical", "high", "medium")}
    return {
        "agent": AGENT_ID, "version": AGENT_VERSION, "workspace": str(root),
        "files_inspected": inspected, "findings": findings[:300], "counts": counts,
        "status": "review_required" if findings else "no_findings",
        "mode": "offline static review; not a full penetration test or formal security certification",
    }

def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"DevSecOps static review v{report['version']}: {report['status']}",
        f"Files inspected: {report['files_inspected']}",
        "Findings: " + ", ".join(f"{key}={value}" for key, value in report["counts"].items()),
    ]
    for finding in report["findings"]:
        lines.append(f"- {finding['severity'].upper()} {finding['rule']} {finding['file']}:{finding['line']} — {finding['recommendation']}")
    lines.append("This is an offline static check, not a penetration test or security certification.")
    return "\n".join(lines)
