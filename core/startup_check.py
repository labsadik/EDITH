"""EDITH startup diagnostics and bootstrap for its allowlisted runtime packages."""
from __future__ import annotations

import importlib.util
import sys
from typing import Callable

# These imports are needed by the GUI/voice entrypoint before setup can appear.
STARTUP_IMPORTS = (
    ("sounddevice", "sounddevice"),
    ("PyQt6", "PyQt6"),
    ("google.genai", "google-genai>=2.8.0"),
    ("psutil", "psutil"),
    ("numpy", "numpy"),
    ("requests", "requests"),
)


def missing_startup_dependencies(
    find_spec: Callable[[str], object] = importlib.util.find_spec,
) -> list[tuple[str, str]]:
    """Check import availability without importing audio or GUI dependencies."""
    missing = []
    for module, package in STARTUP_IMPORTS:
        try:
            if find_spec(module) is None:
                missing.append((module, package))
        except (ImportError, ModuleNotFoundError, ValueError):
            missing.append((module, package))
    return missing


def format_install_help(missing: list[tuple[str, str]]) -> str:
    names = ", ".join(module for module, _ in missing)
    return (
        f"EDITH cannot start: missing Python modules: {names}.\n"
        "In the project directory, run:\n"
        '  python -m pip install -r requirements.txt\n'
        "Then start EDITH with:\n"
        "  python main.py\n"
        "Use the same Python interpreter for both commands. "
        "Your existing API keys and local-LLM settings are not modified."
    )


def bootstrap_missing_dependencies(
    find_spec: Callable[[str], object] = importlib.util.find_spec,
    install: Callable[[dict, Callable | None], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[tuple[str, str]]:
    """Install only EDITH's declared Python dependencies, then re-check imports.

    This never accepts a package name from model text, a file, or a webpage.
    It is intentionally limited to the static allowlist in ``core.installer``.
    """
    missing = missing_startup_dependencies(find_spec)
    if not missing:
        return []
    if install is None:
        from core.installer import install_for_config
        install = install_for_config
    if log:
        log("SYS: Installing missing EDITH runtime tools: " + ", ".join(pkg for _, pkg in missing))
    install({}, log)
    return missing_startup_dependencies(find_spec)


def check_startup_dependencies() -> None:
    try:
        missing = bootstrap_missing_dependencies(log=lambda message: print(message, file=sys.stderr))
    except Exception as exc:
        missing = missing_startup_dependencies()
        if missing:
            print(f"EDITH dependency bootstrap failed: {type(exc).__name__}", file=sys.stderr)
    if not missing:
        return
    message = format_install_help(missing)
    print(message, file=sys.stderr)
    # A shortcut using pythonw.exe has no visible console for the error.
    if sys.platform == "win32" and sys.executable.lower().endswith("pythonw.exe"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "EDITH — Setup Required", 0x30)
        except Exception:
            pass
    raise SystemExit(2)


if __name__ == "__main__":
    missing = missing_startup_dependencies()
    if missing:
        print(format_install_help(missing))
        raise SystemExit(2)
    print("EDITH startup dependencies are installed.")

