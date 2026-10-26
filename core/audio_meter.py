"""Tiny, dependency-free UI input meter for 16-bit little-endian PCM.

This is a display-only intensity estimate, not speech recognition or proof
that a cloud provider received audio. It never stores or logs audio.
"""
from __future__ import annotations

import math
import struct


def pcm16_level(data: bytes | bytearray | memoryview) -> float:
    """Return a noise-gated 0..1 intensity from a PCM16 mono audio chunk.

    Sample at most 256 values to keep the PortAudio callback inexpensive.
    Empty, malformed and silent chunks produce zero.
    """
    try:
        view = memoryview(data).cast("B")
    except (TypeError, ValueError):
        return 0.0
    samples = len(view) // 2
    if not samples:
        return 0.0

    stride = max(1, (samples + 255) // 256)
    energy = 0.0
    count = 0
    for index in range(0, samples, stride):
        value = struct.unpack_from("<h", view, index * 2)[0]
        energy += value * value
        count += 1
    rms = math.sqrt(energy / count) / 32768.0
    # A gentle gate ignores idle mic hiss; sqrt keeps soft voices visible.
    return min(1.0, math.sqrt(max(0.0, rms - 0.003) * 10.0))
