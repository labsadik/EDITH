"""Small, deterministic reconnect policy for the Gemini Live session."""
from __future__ import annotations


def retry_delay(previous: object, *, initial: int = 3, maximum: int = 60) -> int:
    """Return a bounded delay; zero means a fresh retry sequence.

    Saving a new API key or completing a healthy session resets the previous
    delay to zero. A subsequent failure must still wait before retrying.
    """
    try:
        elapsed = float(previous)
    except (TypeError, ValueError, OverflowError):
        elapsed = 0
    if not 0 < elapsed < float("inf"):
        return initial
    return min(maximum, max(initial, int(elapsed) * 2))
