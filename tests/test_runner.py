from __future__ import annotations

import math
from typing import cast

import pytest

from benchmark.codecs.json_codec import JsonCodec
from benchmark.generate.records import PayloadProfile, golden_small_event
from benchmark.metrics.compress import CompressionAlg
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
    assert report["report_version"] == 8
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


def test_build_report_s2_includes_registry_stats() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S2",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=2,
        seed=1,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    assert report["report_version"] == 8
    assert report["scenario"]["tier"] == "S2"
    assert "s2" in report["scenario"]
    row = report["results"][0]
    assert row["tier"] == "S2"
    s2 = row["s2_registry"]
    assert s2["fetch_new_tcp_each_iteration"]["mean_s"] >= 0
    assert s2["fetch_reused_connection"]["mean_s"] >= 0


def test_build_report_s3_producer_batch() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S3",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=2,
        seed=2,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=4,
    )
    assert report["scenario"]["batch_size"] == 4
    assert report["scenario"]["s3_s4"]["batch_size"] == 4
    row = report["results"][0]
    assert row["tier"] == "S3"
    bb = row["s3_producer_batch"]["batch_build_and_join"]
    assert bb["mean_s"] >= 0
    assert row["s3_producer_batch"]["batch_size"] == 4


def test_build_report_s4_consumer_batch() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S4",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=2,
        seed=3,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=4,
    )
    assert report["scenario"]["batch_size"] == 4
    row = report["results"][0]
    assert row["tier"] == "S4"
    bd = row["s4_consumer_batch"]["batch_decode"]
    assert bd["mean_s"] >= 0


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


def test_build_report_all_profiles_all_formats_s0_matrix() -> None:
    report = build_report(
        profiles=list(PayloadProfile),
        tier="S0",
        formats=["avro", "protobuf", "json"],
        compression="zstd",
        warmup=0,
        iterations=1,
        seed=3,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    assert len(report["results"]) == 12
    keys = {(row["payload_profile"], row["codec"]) for row in report["results"]}
    profiles = {p.value for p in PayloadProfile}
    codecs = {"avro", "protobuf", "json"}
    assert keys == {(p, c) for p in profiles for c in codecs}
    assert report["scenario"]["formats"] == ["avro", "protobuf", "json"]
    assert report["scenario"]["payload_profiles"] == [p.value for p in PayloadProfile]
    for row in report["results"]:
        assert row["tier"] == "S0"
        gz = row["compressed_payload_bytes"]["gzip"]["bytes"]
        zs = row["compressed_payload_bytes"]["zstd"]["bytes"]
        assert gz > 0 and zs > 0


@pytest.mark.parametrize("compression", ["gzip", "zstd"])
def test_build_report_all_profiles_all_formats_s1_matrix(compression: str) -> None:
    comp = cast(CompressionAlg, compression)
    report = build_report(
        profiles=list(PayloadProfile),
        tier="S1",
        formats=["avro", "protobuf", "json"],
        compression=comp,
        warmup=0,
        iterations=1,
        seed=2,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    assert len(report["results"]) == 12
    assert report["scenario"]["s1"]["timed_compression_algorithm"] == compression
    for row in report["results"]:
        assert row["tier"] == "S1"
        assert row["compression"] == compression
        assert row["s1_timed_compression"]["timed_algorithm"] == compression
        assert row["compressed_size_bytes"] > 0
        assert row["raw_size_bytes"] > 0
        ratio = row["s1_timed_compression"]["ratio_compressed_to_raw"]
        assert isinstance(ratio, (int, float))
        assert ratio == ratio  # not NaN
