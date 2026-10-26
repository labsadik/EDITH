"""Read-only EDITH platform and audio compatibility probe.

No settings or credentials are read or changed. This reports usable *default*
audio devices for the exact PCM formats required by Gemini Live; device names
and identifiers are deliberately not printed. Manual OS/device verification
is still necessary for GUI control, camera access and wake/sleep behavior.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from typing import Any


def audio_compatibility(sounddevice: Any = None) -> dict[str, str]:
    """Check default 16 kHz input and 24 kHz output without opening streams."""
    if sounddevice is None:
        try:
            import sounddevice as sounddevice
        except (ImportError, OSError) as exc:
            return {
                "microphone": "unavailable: audio library could not be loaded",
                "speaker": "unavailable: audio library could not be loaded",
            }

    results: dict[str, str] = {}
    for label, kind, method, rate in (
        ("microphone", "input", "check_input_settings", 16000),
        ("speaker", "output", "check_output_settings", 24000),
    ):
        try:
            device = sounddevice.query_devices(kind=kind)
            if not device:
                results[label] = "unavailable: no default device"
                continue
            getattr(sounddevice, method)(samplerate=rate, channels=1, dtype="int16")
            results[label] = f"ready: mono PCM16 at {rate} Hz"
        except Exception as exc:
            results[label] = (
                f"unavailable or unsupported PCM rate ({type(exc).__name__}); "
                "text and remote modes can still work"
            )
    return results


def desktop_compatibility(
    os_name: str | None = None,
    environment: dict[str, str] | None = None,
) -> str:
    """Identify supported desktop families without pretending to test GUI access."""
    system = os_name if os_name is not None else platform.system()
    env = os.environ if environment is None else environment
    if system == "Windows":
        return "Windows desktop (GUI permissions and DPI require on-device test)"
    if system == "Darwin":
        return "macOS desktop (Accessibility/Screen Recording permissions may be required)"
    if system == "Linux":
        if env.get("WAYLAND_DISPLAY"):
            return "Linux Wayland (some global desktop-control operations are restricted)"
        if env.get("DISPLAY"):
            return "Linux X11 (desktop permissions and window-manager support vary)"
        return "Linux: no active graphical display detected"
    return "OS not validated: desktop-control support is not guaranteed"


def report() -> dict[str, object]:
    """A deliberately nonsensitive summary; never include paths, keys or devices."""
    data: dict[str, object] = {
        "product": "EDITH",
        "os": platform.system(),
        "architecture": platform.machine(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "logical_cpu_count": os.cpu_count(),
        "desktop": desktop_compatibility(),
        "note": (
            "Local LLM may run on CPU; GPU availability, model memory and "
            "driver support must be checked with the chosen model provider. "
            "Gemini Live needs a working network connection and API key. "
            "Not all OS releases or devices can be guaranteed compatible."
        ),
    }
    data.update(audio_compatibility())
    return data


def main() -> None:
    print(json.dumps(report(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
