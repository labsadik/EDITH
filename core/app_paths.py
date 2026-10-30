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


def config_path() -> Path:
    """Return a writable config path and safely migrate a legacy bundled config."""
    if not is_frozen():
        return resource_dir() / "config" / "api_keys.json"

    target = app_data_dir() / "config" / "api_keys.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    legacy = install_dir() / "config" / "api_keys.json"
    if not target.exists() and legacy.is_file():
        # Keep the installation copy untouched. A user-specific copy avoids
        # cross-account credential sharing when the app is installed for all users.
        temporary = target.with_name(target.name + ".migration")
        shutil.copy2(legacy, temporary)
        temporary.replace(target)
    return target


__all__ = ["app_data_dir", "config_path", "install_dir", "is_frozen", "resource_dir"]
