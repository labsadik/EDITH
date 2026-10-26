"""Regression coverage for bounded, privacy-safe latency observations."""
from __future__ import annotations

import unittest

from core.latency_metrics import LatencyMetrics
from core.reconnect_policy import retry_delay
from edith.platform.permissions import tool_tier
from core.task_scheduler import parallel_read_only


class LatencyMetricsTests(unittest.TestCase):
    def test_percentiles_are_deterministic_and_recent_samples_are_bounded(self):
        metrics = LatencyMetrics(samples_per_metric=8)
        for sample in range(1, 11):
            self.assertTrue(metrics.record("Text to First Audio", sample))
        summary = metrics.summary()["text_to_first_audio"]
        self.assertEqual(summary["count"], 8)
        self.assertEqual(summary["min_ms"], 3)
        self.assertEqual(summary["p50_ms"], 6)
        self.assertEqual(summary["p95_ms"], 10)

    def test_invalid_duration_and_unbounded_metric_names_are_rejected(self):
        metrics = LatencyMetrics(samples_per_metric=8, metrics_limit=1)
        self.assertFalse(metrics.record("bad", -1))
        self.assertFalse(metrics.record("bad", "not-a-number"))
        self.assertTrue(metrics.record("one", 10))
        self.assertFalse(metrics.record("two", 20))

    def test_human_readable_report_has_no_request_content(self):
        metrics = LatencyMetrics(samples_per_metric=8)
        metrics.record("tool.system_status", 42)
        report = metrics.format()
        self.assertIn("p50=42 ms", report)
        self.assertNotIn("prompt", report.lower())

    def test_metrics_tool_is_read_only_and_requires_no_confirmation(self):
        self.assertEqual(tool_tier("performance_metrics", {}), 0)
        self.assertTrue(parallel_read_only("performance_metrics", {}))


class ReconnectPolicyTests(unittest.TestCase):
    def test_first_failure_after_reset_never_spins(self):
        for previous in (None, 0, -1, "invalid", float("nan")):
            self.assertEqual(retry_delay(previous), 3)

    def test_consecutive_failures_are_bounded_and_recovery_resets(self):
        delays = [retry_delay(0)]
        for _ in range(8):
            delays.append(retry_delay(delays[-1]))
        self.assertEqual(delays[:5], [3, 6, 12, 24, 48])
        self.assertEqual(delays[-1], 60)
        self.assertEqual(retry_delay(0), 3)

    def test_application_rethrows_outer_cancellation_and_records_retry(self):
        from pathlib import Path
        main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn("except asyncio.CancelledError:\n                # asyncio.run()", main)
        self.assertIn('self._latency_metrics.record("live_reconnect_wait", delay * 1000)', main)


if __name__ == "__main__":
    unittest.main()
