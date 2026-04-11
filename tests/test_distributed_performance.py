"""Large-payload and batch-oriented checks aligned with distributed / Kafka-style load.

These tests do **not** spin up a real broker or cluster. They use the existing harness
tiers as proxies:

- **Wire size (S0)** — broker retention and cross-AZ replication favor compact payloads.
- **Tier S1** — timed compression on the serialized blob (producer-ish CPU + bytes).
- **Tier S3** — in-memory producer-style batch encode + ``bytes.join`` (throughput
  proxy).
- **Tier S4** — prefetched batch decode (consumer-ish throughput proxy).

Small-payload micro-benchmarks can favor highly tuned JSON; these cases stress sizes and
batch paths where binary codecs are expected to dominate **on this fixture set**.
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
def test_large_profile_s3_producer_batch_higher_throughput_binary_vs_json() -> None:
    """S3 batch: binary codecs have higher effective records/s than JSON (large)."""

    report = build_report(
        profiles=[PayloadProfile.large],
        tier=cast(ReportTier, "S3"),
        formats=["avro", "protobuf", "json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=1,
        iterations=5,
        seed=42,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=32,
    )
    j_rps = float(
        _row_for(report, profile="large", tier="S3", codec="json")["s3_producer_batch"][
            "effective_records_per_s"
        ],
    )
    a_rps = float(
        _row_for(report, profile="large", tier="S3", codec="avro")["s3_producer_batch"][
            "effective_records_per_s"
        ],
    )
    p_rps = float(
        _row_for(report, profile="large", tier="S3", codec="protobuf")[
            "s3_producer_batch"
        ]["effective_records_per_s"],
    )
    for label, x in ("json", j_rps), ("avro", a_rps), ("protobuf", p_rps):
        assert (
            x == x and x > 0 and not math.isinf(x)
        ), f"{label} effective_records_per_s"
    assert a_rps > j_rps * 2.0 and p_rps > j_rps * 2.0, (
        "expected binary codecs >> JSON on S3 batch for large profile "
        f"(json={j_rps:.0f}, avro={a_rps:.0f}, protobuf={p_rps:.0f})"
    )


@pytest.mark.distributed
def test_large_profile_s4_consumer_batch_decode_binary_faster_than_json() -> None:
    """S4 batch decode: binary codecs exceed JSON effective records/s (large)."""

    report = build_report(
        profiles=[PayloadProfile.large],
        tier=cast(ReportTier, "S4"),
        formats=["avro", "protobuf", "json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=1,
        iterations=5,
        seed=42,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=32,
    )
    j_rps = float(
        _row_for(report, profile="large", tier="S4", codec="json")["s4_consumer_batch"][
            "effective_records_per_s"
        ],
    )
    a_rps = float(
        _row_for(report, profile="large", tier="S4", codec="avro")["s4_consumer_batch"][
            "effective_records_per_s"
        ],
    )
    p_rps = float(
        _row_for(report, profile="large", tier="S4", codec="protobuf")[
            "s4_consumer_batch"
        ]["effective_records_per_s"],
    )
    for label, x in ("json", j_rps), ("avro", a_rps), ("protobuf", p_rps):
        assert (
            x == x and x > 0 and not math.isinf(x)
        ), f"{label} effective_records_per_s"
    assert a_rps > j_rps * 2.0 and p_rps > j_rps * 2.0, (
        "expected binary codecs >> JSON on S4 batch decode for large profile "
        f"(json={j_rps:.0f}, avro={a_rps:.0f}, protobuf={p_rps:.0f})"
    )


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
