"""Bounded, thread-safe local latency observations for release diagnostics.

Samples contain durations only: no prompts, audio, tool arguments, outputs,
credentials or user identity. Percentiles describe observed samples on this
device; they are not a promise of cloud or hardware performance.
"""
from __future__ import annotations

from collections import deque
import math
import re
import threading
from typing import Any


_NAME = re.compile(r"[^a-z0-9_.-]+")


class LatencyMetrics:
    def __init__(self, *, samples_per_metric: int = 256, metrics_limit: int = 32):
        if not 8 <= samples_per_metric <= 4096:
            raise ValueError("samples_per_metric must be between 8 and 4096")
        self._samples_per_metric = samples_per_metric
        self._metrics_limit = max(1, int(metrics_limit))
        self._values: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _name(name: object) -> str:
        value = _NAME.sub("_", str(name).casefold()).strip("_.-")
        return value[:80] or "unknown"

    def record(self, name: object, milliseconds: object) -> bool:
        try:
            value = float(milliseconds)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(value) or value < 0 or value > 86_400_000:
            return False
        key = self._name(name)
        with self._lock:
            if key not in self._values:
                if len(self._values) >= self._metrics_limit:
                    # Keep established metric names stable rather than allowing
                    # unbounded model-created labels to consume memory.
                    return False
                self._values[key] = deque(maxlen=self._samples_per_metric)
            self._values[key].append(value)
        return True

    @staticmethod
    def _percentile(values: list[float], fraction: float) -> float:
        index = max(0, min(len(values) - 1, math.ceil(len(values) * fraction) - 1))
        return values[index]

    def summary(self, name: str | None = None) -> dict[str, dict[str, int]]:
        key = self._name(name) if name is not None else None
        with self._lock:
            items = ((key, self._values.get(key, ())) if key else self._values.items())
            snapshot = {metric: list(samples) for metric, samples in items if samples}
        result: dict[str, dict[str, int]] = {}
        for metric, samples in snapshot.items():
            values = sorted(samples)
            result[metric] = {
                "count": len(values),
                "min_ms": round(values[0]),
                "p50_ms": round(self._percentile(values, .50)),
                "p95_ms": round(self._percentile(values, .95)),
                "max_ms": round(values[-1]),
                "mean_ms": round(sum(values) / len(values)),
            }
        return result

    def format(self) -> str:
        data: dict[str, Any] = self.summary()
        if not data:
            return "No local latency samples have been recorded yet."
        lines = ["Local observed latency (not a guaranteed response time):"]
        for name, stats in data.items():
            lines.append(
                f"- {name}: n={stats['count']}, p50={stats['p50_ms']} ms, "
                f"p95={stats['p95_ms']} ms, range={stats['min_ms']}–{stats['max_ms']} ms"
            )
        return "\n".join(lines)


__all__ = ["LatencyMetrics"]
