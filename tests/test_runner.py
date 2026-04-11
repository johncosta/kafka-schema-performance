from __future__ import annotations

import math
from typing import cast

import pytest

from benchmark.codecs.json_codec import JsonCodec
from benchmark.generate.records import PayloadProfile, golden_small_event
from benchmark.metrics.compress import CompressionAlg
from benchmark.scenarios.runner import (
    ALL_BENCHMARK_TIERS,
    ReportTier,
    ScenarioTier,
    bench_codec,
    build_report,
)


def test_bench_codec_smoke_s0() -> None:
    r = bench_codec(
        JsonCodec(),
        golden_small_event(),
        tier="S0",
        compression="zstd",
        warmup=2,
        iterations=10,
    )
    assert r["codec"] == "json"
    assert r["raw_size_bytes"] > 0
    assert r["raw_size_bytes"] == r["compressed_size_bytes"]
    assert r["raw_encoded_bytes"]["n"] == 10
    assert r["compressed_payload_bytes"]["gzip"]["bytes"] > 0
    assert r["derived_cost"]["reference_formulas"]
    assert r["allocations"] is None
    rt = r["round_trip"]
    assert "round_trip_mb_per_s" in rt
    assert not math.isnan(rt["round_trip_mb_per_s"])


def test_bench_codec_tracemalloc_sample() -> None:
    r = bench_codec(
        JsonCodec(),
        golden_small_event(),
        tier="S0",
        compression="zstd",
        warmup=1,
        iterations=2,
        tracemalloc_sample=True,
    )
    assert r["allocations"] is not None
    assert r["allocations"]["peak_bytes_traced"] >= 0


def test_bench_codec_s1_zstd_timed_compression() -> None:
    r = bench_codec(
        JsonCodec(),
        golden_small_event(),
        tier="S1",
        compression="zstd",
        warmup=1,
        iterations=4,
        s1_zstd_level=1,
    )
    assert r["tier"] == "S1"
    assert r["s1_timed_compression"] is not None
    assert r["s1_timed_compression"]["timed_algorithm"] == "zstd"
    assert r["s1_timed_compression"]["zstd_level_used"] == 1
    assert r["compressed_size_bytes"] <= r["raw_size_bytes"]
    assert "encode_compressed_wire_mb_per_s" in r["encode"]
    assert "decode_compressed_input_mb_per_s" in r["decode"]


def test_bench_codec_confluent_envelope() -> None:
    r = bench_codec(
        JsonCodec(),
        golden_small_event(),
        tier="S0",
        compression="zstd",
        warmup=0,
        iterations=2,
        include_confluent_envelope=True,
        confluent_prefix_bytes=5,
    )
    assert r["kafka_shaped"] is not None
    assert r["kafka_shaped"]["total_value_bytes"] == r["raw_size_bytes"] + 5


def test_bench_codec_s3_smoke() -> None:
    r = bench_codec(
        JsonCodec(),
        golden_small_event(),
        tier="S3",
        compression="zstd",
        warmup=1,
        iterations=2,
        batch_size=3,
    )
    assert r["tier"] == "S3"
    assert r["s3_producer_batch"]["batch_size"] == 3


def test_build_report_tier_all_merges_s0_through_s4() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier=cast(ReportTier, "all"),
        formats=["json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=0,
        iterations=1,
        seed=5,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=4,
    )
    assert report["report_version"] == 9
    assert report["scenario"]["tier"] == "all"
    assert report["scenario"]["tiers_executed"] == list(ALL_BENCHMARK_TIERS)
    assert len(report["results"]) == 5
    tiers_in_rows = {str(r["tier"]) for r in report["results"]}
    assert tiers_in_rows == set(ALL_BENCHMARK_TIERS)


@pytest.mark.parametrize("tier", ["S0", "S1", "S2", "S3", "S4"])
@pytest.mark.parametrize("compression", ["gzip", "zstd"])
def test_build_report_exhaustive_matrix_all_profiles_formats_compression(
    tier: str,
    compression: str,
) -> None:
    """Every tier × gzip/zstd × all payload profiles × avro/protobuf/json."""

    t = cast(ScenarioTier, tier)
    comp = cast(CompressionAlg, compression)
    seed = (hash((tier, compression)) % 2_000_000_000) + 1
    report = build_report(
        profiles=list(PayloadProfile),
        tier=t,
        formats=["avro", "protobuf", "json"],
        compression=comp,
        warmup=0,
        iterations=1,
        seed=seed,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=4,
    )
    assert report["report_version"] == 8
    assert "limitations" in report
    assert report["limitations"]["summary"]
    assert "artifact_integrity" in report
    assert "measurement" in report
    assert report["scenario"]["tier"] == tier
    assert report["scenario"]["compression"] == compression
    assert report["scenario"]["formats"] == ["avro", "protobuf", "json"]
    assert report["scenario"]["payload_profiles"] == [p.value for p in PayloadProfile]
    assert len(report["results"]) == 12

    profiles = {p.value for p in PayloadProfile}
    codecs = {"avro", "protobuf", "json"}
    keys = {(row["payload_profile"], row["codec"]) for row in report["results"]}
    assert keys == {(p, c) for p in profiles for c in codecs}

    if tier == "S1":
        assert "s1" in report["scenario"]
        assert report["scenario"]["s1"]["timed_compression_algorithm"] == compression
        for row in report["results"]:
            assert row["tier"] == "S1"
            assert row["compression"] == compression
            assert row["s1_timed_compression"]["timed_algorithm"] == compression
            ratio = row["s1_timed_compression"]["ratio_compressed_to_raw"]
            assert isinstance(ratio, (int, float))
            assert ratio == ratio
    else:
        for row in report["results"]:
            assert row["tier"] == tier
            assert row["compression"] == "none"

    if tier == "S0":
        assert "s1" not in report["scenario"]
        for row in report["results"]:
            gz = row["compressed_payload_bytes"]["gzip"]["bytes"]
            zs = row["compressed_payload_bytes"]["zstd"]["bytes"]
            assert gz > 0 and zs > 0
    elif tier == "S2":
        assert "s2" in report["scenario"]
        for row in report["results"]:
            s2 = row["s2_registry"]
            assert s2["fetch_new_tcp_each_iteration"]["mean_s"] >= 0
            assert s2["fetch_reused_connection"]["mean_s"] >= 0
    elif tier == "S3":
        assert report["scenario"]["batch_size"] == 4
        assert report["scenario"]["s3_s4"]["batch_size"] == 4
        for row in report["results"]:
            bb = row["s3_producer_batch"]["batch_build_and_join"]
            assert bb["mean_s"] >= 0
            assert row["s3_producer_batch"]["batch_size"] == 4
    elif tier == "S4":
        assert report["scenario"]["batch_size"] == 4
        for row in report["results"]:
            bd = row["s4_consumer_batch"]["batch_decode"]
            assert bd["mean_s"] >= 0
            assert row["s4_consumer_batch"]["batch_size"] == 4
