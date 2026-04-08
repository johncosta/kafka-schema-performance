from __future__ import annotations

from benchmark.metrics.stats import mb_per_second, summarize_times


def test_summarize_times_percentiles() -> None:
    samples = [0.10, 0.20, 0.15, 0.12, 0.11]
    s = summarize_times(samples)
    assert s["mean_s"] > 0
    assert s["p50_s"] <= s["p90_s"] <= s["p99_s"]


def test_mb_per_second() -> None:
    m = mb_per_second(0.001, 1024 * 1024)
    assert 900 < m < 1100
