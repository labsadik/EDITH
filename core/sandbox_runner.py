"""Fail-closed Python bridge to EDITH's local Rust process sandbox."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
CARGO_MANIFEST = ROOT / "sandbox-rs" / "Cargo.toml"
BUILD_DIR = ROOT / "sandbox-rs" / "target" / "release"
_BUILD_LOCK = __import__("threading").Lock()


class SandboxUnavailable(RuntimeError):
    """The native sandbox could not be built or its OS backend is unavailable."""


def sandbox_binary() -> Path:
    name = "edith-sandbox.exe" if os.name == "nt" else "edith-sandbox"
    configured = os.environ.get("EDITH_SANDBOX_BIN", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return BUILD_DIR / name


def ensure_sandbox_ready() -> Path:
    """Build the audited local Rust helper once; never fall back to host execution."""
    binary = sandbox_binary()
    if binary.is_file():
        return binary
    with _BUILD_LOCK:
        if binary.is_file():
            return binary
        cargo = shutil.which("cargo")
        if not cargo:
            raise SandboxUnavailable(
                "Rust/Cargo is not installed. Install Rust with rustup, then run: "
                "cargo build --release --manifest-path sandbox-rs/Cargo.toml"
            )
        if not CARGO_MANIFEST.is_file():
            raise SandboxUnavailable("The EDITH Rust sandbox source is missing.")
        try:
            result = subprocess.run(
                [cargo, "build", "--release", "--manifest-path", str(CARGO_MANIFEST)],
                cwd=str(ROOT), capture_output=True, text=True, timeout=900,
                shell=False, check=False,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxUnavailable("Rust sandbox build timed out; no project command was executed.") from exc
        if result.returncode != 0 or not binary.is_file():
            detail = (result.stderr or result.stdout or "Cargo build failed")[-4000:]
            raise SandboxUnavailable("Rust sandbox build failed; execution was blocked.\\n" + detail)
    return binary


def ensure_project_venv(project_dir: str | Path) -> Path:
    """Create an isolated project virtual environment before sandboxed builds."""
    root = Path(project_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=(os.name != "nt")).create(str(target))
    if not python.is_file():
        raise SandboxUnavailable("Project virtual environment could not be created.")
    return python


def run_sandboxed(
    argv: Sequence[str | os.PathLike[str]], *, workspace: str | Path,
    timeout: int = 60, network: bool = False,
    read_only_paths: Sequence[str | Path] = (),
    prepend_paths: Sequence[str | Path] = (),
) -> subprocess.CompletedProcess[str]:
    """Run an exact argv vector with workspace-only writes and bounded resources."""
    if not argv:
        raise ValueError("Sandbox command cannot be empty")
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Sandbox workspace must be an existing directory")
    binary = ensure_sandbox_ready()
    command = [str(binary), "run", "--workspace", str(root),
               "--timeout", str(max(1, min(int(timeout), 3600))),
               "--network", "allow" if network else "deny"]
    for path in read_only_paths:
        candidate = Path(path).expanduser().resolve()
        if candidate.exists():
            command.extend(["--read-only", str(candidate)])
    for path in prepend_paths:
        candidate = Path(path).expanduser().resolve()
        if candidate.is_dir():
            command.extend(["--path-dir", str(candidate)])
    args = [str(item) for item in argv]
    command.append("--")
    command.extend(args)
    env = os.environ.copy()
    if prepend_paths:
        prefix = os.pathsep.join(str(Path(path).expanduser().resolve()) for path in prepend_paths)
        env["PATH"] = prefix + os.pathsep + env.get("PATH", "")
    try:
        result = subprocess.run(
            command, cwd=str(root), env=env, capture_output=True, text=True,
            timeout=max(10, int(timeout) + 20), shell=False, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxUnavailable("Sandbox supervisor timed out; child execution was terminated.") from exc
    if result.returncode == 125:
        raise SandboxUnavailable((result.stderr or "OS sandbox could not be enforced")[-4000:])
    return result


def run_project_command(
    command: str, *, workspace: str | Path, timeout: int = 60,
    network: bool = False, python_executable: str | Path | None = None,
) -> str:
    """Run a project command through an OS shell *inside* the sandbox."""
    root = Path(workspace).expanduser().resolve()
    if os.name == "nt":
        shell = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "System32" / "cmd.exe"
        argv = [str(shell), "/d", "/s", "/c", command]
    else:
        shell = Path("/bin/sh")
        argv = [str(shell), "-lc", command]
    readonly = [shell.parent]
    prepend = []
    if python_executable:
        python_path = Path(python_executable).expanduser().resolve()
        prepend.append(python_path.parent)
        if os.name == "nt":
            readonly.append(python_path.parent)
        else:
            readonly.append(python_path.parent)
    try:
        result = run_sandboxed(
            argv, workspace=root, timeout=timeout, network=network,
            read_only_paths=readonly, prepend_paths=prepend,
        )
    except SandboxUnavailable as exc:
        return f"Execution failed: Rust sandbox unavailable; host execution was not attempted. {exc}"
    output = (result.stdout or "") + ("\n[stderr]\n" + result.stderr if result.stderr else "")
    if result.returncode != 0:
        return f"Execution failed (exit {result.returncode}).\n{output[-12000:]}"
    return output[-12000:] or "Command completed with no output."


__all__ = [
    "SandboxUnavailable", "ensure_project_venv", "ensure_sandbox_ready",
    "run_project_command", "run_sandboxed", "sandbox_binary",
]
