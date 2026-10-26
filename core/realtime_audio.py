"""Bound realtime microphone backlog without blocking the asyncio event loop.

Call this from the event-loop thread only. Audio callbacks should schedule the
function with loop.call_soon_threadsafe, never manipulate asyncio.Queue directly.
Under network congestion the oldest untransmitted chunk is discarded, so EDITH
does not respond to seconds-old audio once the connection catches up.
"""
import asyncio
from typing import Any


def enqueue_latest_audio(queue: asyncio.Queue | None, chunk: Any) -> bool:
    """Enqueue a chunk immediately; replace the oldest chunk when full.

    Returns True if the new chunk was accepted. Returns False for a missing
    queue or in the unlikely event of a concurrent capacity change.
    """
    if queue is None:
        return False
    try:
        queue.put_nowait(chunk)
        return True
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(chunk)
            return True
        except asyncio.QueueFull:
            return False
