"""Non-blocking OS-theme observation for the native EDITH UI.

Theme polling is an application presentation concern, not a user-requested
tool action.  It deliberately uses the platform controller's inexpensive
theme probe directly so a two-second poll does not fill the audit log.
"""
from __future__ import annotations

import threading
from collections.abc import Callable


def normalise_theme(value: object, fallback: str = "dark") -> str:
    """Return the only two UI themes that EDITH renders."""
    theme = str(value or "").strip().lower()
    return theme if theme in {"dark", "light"} else fallback


class SystemThemeMonitor:
    """Read the current platform appearance off the UI thread.

    ``callback`` may run on this worker thread. Qt callers must relay it
    through a signal before touching widgets.
    """

    def __init__(self, callback: Callable[[str], None], *, interval: float = 2.0,
                 read_theme: Callable[[], object] | None = None):
        self._callback = callback
        self._interval = max(0.25, float(interval))
        self._read_theme = read_theme or self._platform_theme
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: str | None = None

    @staticmethod
    def _platform_theme() -> object:
        from edith.platform import get_controller
        class _NoopAudit:
            def write(self, *_args, **_kwargs):
                return None
        controller = get_controller(audit=_NoopAudit())
        # ``_op_theme`` contains no mutation, permission prompt or subprocess
        # tracking. The public ``theme()`` route is retained for explicit tool
        # calls, where an audit receipt is required.
        return controller._op_theme()  # noqa: SLF001 - deliberate monitor hook

    def _sample(self) -> str:
        try:
            value = self._read_theme()
            if isinstance(value, dict):
                value = value.get("theme")
            return normalise_theme(value)
        except Exception:
            return "dark"

    def _run(self) -> None:
        while not self._stop.is_set():
            theme = self._sample()
            if theme != self._last:
                self._last = theme
                try:
                    self._callback(theme)
                except Exception:
                    # A UI may disappear while a final callback is pending.
                    pass
            self._stop.wait(self._interval)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="edith-theme", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=min(1.0, self._interval + 0.1))

