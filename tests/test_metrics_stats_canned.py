from __future__ import annotations

import math

import pytest

from benchmark.metrics.compress import compress, decompress
from benchmark.metrics.stats import summarize_times


def test_summarize_times_canned_sample_percentiles() -> None:
    """PRD §6.6.1: stats helpers are deterministic for known inputs (no wall clock)."""

    samples = [0.010, 0.020, 0.030, 0.040, 0.050]
    s = summarize_times(samples)
    assert s["mean_s"] == pytest.approx(0.03)
    assert s["p50_s"] == pytest.approx(0.03)
    assert s["p90_s"] == pytest.approx(0.046)
    assert s["p99_s"] == pytest.approx(0.0496)
    assert s["records_per_s"] == pytest.approx(1.0 / 0.03)
    assert not math.isnan(s["p99_s"])


def test_compress_decompress_roundtrip_zstd_isolated_from_codecs() -> None:
    raw = b"payload-bytes" * 400
    z = compress("zstd", raw, level=1)
    assert len(z) < len(raw)
    assert decompress("zstd", z) == raw


def test_compress_decompress_roundtrip_gzip_isolated_from_codecs() -> None:
    raw = b"hello" * 200
    g = compress("gzip", raw, level=1)
    assert decompress("gzip", g) == raw
