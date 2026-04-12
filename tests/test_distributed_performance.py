"""Large-payload checks using in-process harness tiers (no broker).

Broker-backed Kafka-protocol benchmarks live under ``tests/integration/`` (see
``docker/docker-compose.kafka.yml`` and ``KSP_KAFKA_BOOTSTRAP``).

These tests use harness tiers as **proxies** for sizing only:

- **Wire size (S0)** — compact payloads matter for retention and replication.
- **Tier S1** — timed compression on the serialized blob (producer-ish CPU + bytes).

For produce/consume over a real Kafka-compatible broker, see ``@pytest.mark.kafka``
tests and the ``kafka_e2e`` block merged into ``report.json``.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from benchmark.codecs.json_codec import JsonCodec
from benchmark.generate.records import PayloadProfile, sample_event
from benchmark.metrics.compress import CompressionAlg
from benchmark.scenarios.runner import ReportTier, bench_codec, build_report


def _mean_raw_bytes(row: dict[str, Any]) -> float:
    re = row.get("raw_encoded_bytes")
    if isinstance(re, dict):
        m = re.get("mean")
        if isinstance(m, (int, float)) and m == m:
            return float(m)
    rs = row.get("raw_size_bytes")
    if isinstance(rs, (int, float)) and rs == rs:
        return float(rs)
    pytest.fail("row missing raw wire size")


def _row_for(
    report: dict[str, Any],
    *,
    profile: str,
    tier: str,
    codec: str,
) -> dict[str, Any]:
    for r in report["results"]:
        if (
            str(r.get("payload_profile")) == profile
            and str(r.get("tier")) == tier
            and str(r.get("codec")) == codec
        ):
            return cast(dict[str, Any], r)
    pytest.fail(f"no row for {profile=} {tier=} {codec=}")


def _assert_s0_row_throughput_matches_wire(row: dict[str, Any]) -> None:
    """S0 rows report ``raw_size_bytes`` plus MB/s and records/s derived from means."""

    raw = int(row["raw_size_bytes"])
    assert raw > 0
    for phase, mb_key in (
        ("encode", "encode_mb_per_s"),
        ("decode", "decode_mb_per_s"),
        ("round_trip", "round_trip_mb_per_s"),
    ):
        block = cast(dict[str, Any], row[phase])
        mean_s = float(block["mean_s"])
        mbps = float(block[mb_key])
        rps = float(block["records_per_s"])
        assert mean_s > 0
        assert mbps == mbps and rps == rps
        assert mbps > 0 and rps > 0
        exp_mb = (raw / mean_s) / (1024.0 * 1024.0)
        exp_rps = 1.0 / mean_s
        assert math.isclose(mbps, exp_mb, rel_tol=1e-5, abs_tol=1e-12)
        assert math.isclose(rps, exp_rps, rel_tol=1e-5, abs_tol=1e-12)


@pytest.mark.distributed
def test_large_profile_raw_wire_json_largest_s0() -> None:
    """Binary codecs use less wire than JSON for the large fixture (S0)."""

    report = build_report(
        profiles=[PayloadProfile.large],
        tier=cast(ReportTier, "S0"),
        formats=["avro", "protobuf", "json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=0,
        iterations=2,
        seed=42,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    j = _mean_raw_bytes(_row_for(report, profile="large", tier="S0", codec="json"))
    a = _mean_raw_bytes(_row_for(report, profile="large", tier="S0", codec="avro"))
    p = _mean_raw_bytes(_row_for(report, profile="large", tier="S0", codec="protobuf"))
    assert j > a and j > p, "expected JSON wire > binary codecs for large profile"
    assert a > 0 and p > 0
    for fmt in ("json", "avro", "protobuf"):
        _assert_s0_row_throughput_matches_wire(
            _row_for(report, profile="large", tier="S0", codec=fmt),
        )


@pytest.mark.distributed
def test_large_profile_s1_zstd_compressed_smaller_for_binary_codecs() -> None:
    """After timed zstd, JSON compressed payload is still larger than binary (S1)."""

    report = build_report(
        profiles=[PayloadProfile.large],
        tier=cast(ReportTier, "S1"),
        formats=["avro", "protobuf", "json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=1,
        iterations=3,
        seed=42,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    j = int(
        _row_for(report, profile="large", tier="S1", codec="json")[
            "compressed_size_bytes"
        ]
    )
    a = int(
        _row_for(report, profile="large", tier="S1", codec="avro")[
            "compressed_size_bytes"
        ]
    )
    p = int(
        _row_for(report, profile="large", tier="S1", codec="protobuf")[
            "compressed_size_bytes"
        ],
    )
    assert j > a and j > p


@pytest.mark.distributed
def test_medium_profile_raw_wire_json_largest_s0() -> None:
    """Between small and large payloads, binary codecs still win on wire footprint."""

    report = build_report(
        profiles=[PayloadProfile.medium],
        tier=cast(ReportTier, "S0"),
        formats=["avro", "protobuf", "json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=0,
        iterations=2,
        seed=7,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    j = _mean_raw_bytes(_row_for(report, profile="medium", tier="S0", codec="json"))
    a = _mean_raw_bytes(_row_for(report, profile="medium", tier="S0", codec="avro"))
    p = _mean_raw_bytes(_row_for(report, profile="medium", tier="S0", codec="protobuf"))
    assert j > a and j > p
    for fmt in ("json", "avro", "protobuf"):
        _assert_s0_row_throughput_matches_wire(
            _row_for(report, profile="medium", tier="S0", codec=fmt),
        )


def test_bench_codec_s3_s4_batch_metrics_exist_for_large_single_codec() -> None:
    """Batch tiers expose positive effective_records_per_s for JSON large payload."""

    event = sample_event(PayloadProfile.large, 99)
    codec = JsonCodec()
    s3 = bench_codec(
        codec,
        event,
        tier="S3",
        compression="zstd",
        warmup=0,
        iterations=2,
        batch_size=8,
    )
    s4 = bench_codec(
        codec,
        event,
        tier="S4",
        compression="zstd",
        warmup=0,
        iterations=2,
        batch_size=8,
    )
    s3_eff = float(s3["s3_producer_batch"]["effective_records_per_s"])
    s4_eff = float(s4["s4_consumer_batch"]["effective_records_per_s"])
    assert s3_eff == s3_eff and s3_eff > 0
    assert s4_eff == s4_eff and s4_eff > 0
