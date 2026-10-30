"""Fail-closed Python bridge to EDITH's local OS-enforced Rust sandbox."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import venv
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
CARGO_MANIFEST = ROOT / "sandbox-rs" / "Cargo.toml"
BUILD_DIR = ROOT / "sandbox-rs" / "target" / "release"
_BUILD_LOCK = threading.Lock()
_TOOL_NAMES = (
    "python", "python3", "node", "npm", "npx", "git", "cargo", "rustc",
    "dotnet", "java", "go", "gcc", "clang", "cmake", "make", "ffmpeg",
)


class SandboxUnavailable(RuntimeError):
    """The native sandbox could not be built or its OS backend is unavailable."""


def sandbox_binary() -> Path:
    name = "edith-sandbox.exe" if os.name == "nt" else "edith-sandbox"
    configured = os.environ.get("EDITH_SANDBOX_BIN", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return BUILD_DIR / name


def ensure_sandbox_ready() -> Path:
    """Build the local Rust helper once; never fall back to host execution."""
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
            raise SandboxUnavailable(
                "Rust sandbox build timed out; no project command was executed."
            ) from exc
        if result.returncode != 0 or not binary.is_file():
            detail = (result.stderr or result.stdout or "Cargo build failed")[-4000:]
            raise SandboxUnavailable(
                "Rust sandbox build failed; execution was blocked.\n" + detail
            )
    return binary


def ensure_project_venv(project_dir: str | Path) -> Path:
    """Create an isolated project virtual environment before sandboxed builds."""
    root = Path(project_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        venv.EnvBuilder(
            with_pip=True, clear=False, symlinks=(os.name != "nt")
        ).create(str(target))
    if not python.is_file():
        raise SandboxUnavailable("Project virtual environment could not be created.")
    return python


def _runtime_read_paths(workspace: Path) -> list[Path]:
    """Expose only the Python runtime roots required to start the project venv."""
    candidates = [Path(sys.base_prefix), Path(sys.executable).resolve().parent]
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
            key = os.path.normcase(str(resolved))
            if not resolved.exists() or resolved == workspace or workspace in resolved.parents or key in seen:
                continue
            seen.add(key)
            result.append(resolved)
        except OSError:
            continue
    return result


def _tool_runtime_paths(workspace: Path) -> tuple[list[Path], list[Path]]:
    """Allow known installed build tools to be read/executed without exposing whole drives."""
    read_paths: list[Path] = []
    path_dirs: list[Path] = []
    seen: set[str] = set()
    for name in _TOOL_NAMES:
        executable = shutil.which(name)
        if not executable:
            continue
        candidate = Path(executable).expanduser().resolve()
        parent = candidate.parent
        try:
            if candidate.exists() and parent.exists():
                key = os.path.normcase(str(parent))
                if parent != workspace and workspace not in parent.parents and key not in seen:
                    seen.add(key)
                    read_paths.append(parent)
                    path_dirs.append(parent)
        except OSError:
            continue
    return read_paths, path_dirs


def run_sandboxed(
    argv: Sequence[str | os.PathLike[str]], *, workspace: str | Path,
    timeout: int = 60, network: bool = False,
    read_only_paths: Sequence[str | Path] = (),
    prepend_paths: Sequence[str | Path] = (),
) -> subprocess.CompletedProcess[str]:
    """Run exact argv with workspace-only writes, clean child env and bounded time."""
    if not argv:
        raise ValueError("Sandbox command cannot be empty")
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Sandbox workspace must be an existing directory")
    binary = ensure_sandbox_ready()
    limit = max(1, min(int(timeout), 3600))
    command = [
        str(binary), "run", "--workspace", str(root),
        "--timeout", str(limit), "--network", "allow" if network else "deny",
    ]
    exposed: set[str] = set()
    for path in [*read_only_paths, *_runtime_read_paths(root)]:
        try:
            candidate = Path(path).expanduser().resolve()
            key = os.path.normcase(str(candidate))
            if candidate.exists() and candidate != root and root not in candidate.parents and key not in exposed:
                command.extend(["--read-only", str(candidate)])
                exposed.add(key)
        except OSError:
            continue
    path_dirs: list[Path] = []
    path_seen: set[str] = set()
    for path in prepend_paths:
        try:
            candidate = Path(path).expanduser().resolve()
            key = os.path.normcase(str(candidate))
            if candidate.is_dir() and candidate != root and key not in path_seen:
                path_dirs.append(candidate)
                path_seen.add(key)
        except OSError:
            continue
    for path in path_dirs:
        command.extend(["--path-dir", str(path)])
    command.append("--")
    command.extend(str(item) for item in argv)
    # Only the Rust supervisor receives the host environment. Each OS backend
    # constructs a filtered environment for the child process.
    try:
        result = subprocess.run(
            command, cwd=str(root), capture_output=True, text=True,
            timeout=limit + 20, shell=False, check=False,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxUnavailable(
            "Sandbox supervisor timed out; child execution was terminated."
        ) from exc
    if result.returncode == 125:
        raise SandboxUnavailable(
            (result.stderr or "OS sandbox could not be enforced")[-4000:]
        )
    return result


def run_project_command(
    command: str, *, workspace: str | Path, timeout: int = 60,
    network: bool = False, python_executable: str | Path | None = None,
) -> str:
    """Run a project command in the OS sandbox; there is no host-shell fallback."""
    root = Path(workspace).expanduser().resolve()
    if os.name == "nt":
        shell = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "System32" / "cmd.exe"
        argv = [str(shell), "/d", "/s", "/c", command]
    else:
        shell = Path("/bin/sh")
        argv = [str(shell), "-lc", command]

    readonly = [shell.parent, *_runtime_read_paths(root)]
    path_dirs: list[Path] = []
    if python_executable:
        python_path = Path(python_executable).expanduser().resolve()
        if python_path.is_file():
            path_dirs.append(python_path.parent)
            readonly.append(python_path.parent)
    tool_paths, tool_dirs = _tool_runtime_paths(root)
    readonly.extend(tool_paths)
    path_dirs.extend(tool_dirs)
    try:
        result = run_sandboxed(
            argv, workspace=root, timeout=timeout, network=network,
            read_only_paths=readonly, prepend_paths=path_dirs,
        )
    except SandboxUnavailable as exc:
        return (
            "Execution failed: Rust sandbox unavailable; host execution was not attempted. "
            f"{exc}"
        )
    output = (result.stdout or "") + (
        "\n[stderr]\n" + result.stderr if result.stderr else ""
    )
    if result.returncode != 0:
        return f"Execution failed (exit {result.returncode}).\n{output[-12000:]}"
    return output[-12000:] or "Command completed with no output."


__all__ = [
    "SandboxUnavailable", "ensure_project_venv", "ensure_sandbox_ready",
    "run_project_command", "run_sandboxed", "sandbox_binary",
]
