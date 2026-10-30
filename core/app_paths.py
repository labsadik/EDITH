"""Runtime path policy for source and packaged EDITH installations.

Packaged applications are commonly installed under Program Files or /Applications,
which must not be used for per-user credentials and mutable state. Source checkouts
keep their historical in-repository config path for developer compatibility.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Read-only application resources (PyInstaller bundle when frozen)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled).resolve()
    return Path(__file__).resolve().parents[1]


def install_dir() -> Path:
    """Directory containing the executable, or project root in source mode."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return resource_dir()


def app_data_dir() -> Path:
    """Private, writable per-user application data directory."""
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        target = base / "EDITH"
    elif system == "Darwin":
        target = home / "Library" / "Application Support" / "EDITH"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
        target = base / "edith"
    target.mkdir(parents=True, exist_ok=True)
    return target


def writable_config_path(filename: str) -> Path:
    """Return a per-user config file, copying its shipped/legacy default once."""
    name = str(filename or "").strip()
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Config filename must be a single safe path component")
    if not is_frozen():
        return resource_dir() / "config" / name

    target = app_data_dir() / "config" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        # Prefer an existing installation copy (upgrades), then a packaged
        # read-only template. Never delete the source or overwrite user state.
        candidates = (
            install_dir() / "config" / name,
            resource_dir() / "config" / name,
        )
        for source in candidates:
            if source.is_file() and source.resolve() != target.resolve():
                temporary = target.with_name(target.name + ".migration")
                try:
                    shutil.copy2(source, temporary)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
                break
    return target


def config_path() -> Path:
    """Return the writable per-user api_keys.json path."""
    return writable_config_path("api_keys.json")


__all__ = [
    "app_data_dir", "config_path", "install_dir", "is_frozen",
    "resource_dir", "writable_config_path",
]
