"""Regression coverage for bounded, privacy-safe latency observations."""
from __future__ import annotations

import unittest

from core.latency_metrics import LatencyMetrics
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


if __name__ == "__main__":
    unittest.main()
