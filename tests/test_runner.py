from __future__ import annotations

import math

from benchmark.codecs.json_codec import JsonCodec
from benchmark.generate.records import PayloadProfile, golden_small_event
from benchmark.scenarios.runner import bench_codec, build_report


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


def test_build_report_multi_profile_matrix() -> None:
    report = build_report(
        profiles=[
            PayloadProfile.small,
            PayloadProfile.medium,
            PayloadProfile.large,
        ],
        tier="S0",
        formats=["json"],
        compression="zstd",
        warmup=1,
        iterations=2,
        seed=7,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    assert report["report_version"] == 6
    assert "limitations" in report
    assert report["limitations"]["summary"]
    assert "artifact_integrity" in report
    assert report["artifact_integrity"]["method"] == "pip freeze"
    assert report["scenario"]["payload_profiles"] == ["small", "medium", "large"]
    assert len(report["results"]) == 3
    assert {row["payload_profile"] for row in report["results"]} == {
        "small",
        "medium",
        "large",
    }
    assert "measurement" in report
    assert report["scenario"]["size_and_cost"]["gzip_compresslevel"] == 6


def test_build_report_s1_scenario_block() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S1",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=2,
        seed=1,
        rubric_governance=None,
        rubric_maintainability=None,
        s1_zstd_level=5,
    )
    s1 = report["scenario"]["s1"]
    assert isinstance(s1, dict)
    assert s1["timed_compression_algorithm"] == "zstd"
    assert s1["zstd_level_cli"] == 5
