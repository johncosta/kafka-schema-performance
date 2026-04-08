from __future__ import annotations

from benchmark.metrics.compress import DEFAULT_GZIP_COMPRESSLEVEL, DEFAULT_ZSTD_LEVEL
from benchmark.metrics.stats import (
    mb_per_second,
    summarize_byte_lengths,
    summarize_times,
)


def test_summarize_times_percentiles() -> None:
    samples = [0.10, 0.20, 0.15, 0.12, 0.11]
    s = summarize_times(samples)
    assert s["mean_s"] > 0
    assert s["p50_s"] <= s["p90_s"] <= s["p99_s"]


def test_mb_per_second() -> None:
    m = mb_per_second(0.001, 1024 * 1024)
    assert 900 < m < 1100


def test_summarize_byte_lengths_constant() -> None:
    s = summarize_byte_lengths([100] * 10)
    assert s["n"] == 10
    assert s["mean"] == 100.0
    assert s["median"] == 100.0
    assert s["p95"] == 100.0


def test_summarize_byte_lengths_empty() -> None:
    s = summarize_byte_lengths([])
    assert s["n"] == 0


def test_compress_default_levels_constants() -> None:
    assert DEFAULT_GZIP_COMPRESSLEVEL == 6
    assert DEFAULT_ZSTD_LEVEL == 3
