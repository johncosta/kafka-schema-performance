"""Containerized Kafka-protocol benchmarks; merge metrics into report shape.

Assertions treat ``value_bytes`` and produce/consume **throughput** (msg/s, MB/s)
as first-class performance metrics: they must be positive, finite, and
internally consistent with wall times and message counts.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from benchmark.codecs.base import Codec
from benchmark.generate.records import PayloadProfile, sample_event
from benchmark.integration.kafka_e2e import (
    attach_kafka_e2e_to_report,
    benchmark_kafka_case,
    build_kafka_e2e_block,
)
from benchmark.models.event import AnalyticsEvent
from benchmark.scenarios.runner import codec_for_profile


def _serialize_factory(codec: Codec, event: AnalyticsEvent) -> Callable[[], bytes]:
    return lambda: codec.encode(event)


def _assert_kafka_e2e_size_and_throughput(
    row: dict[str, Any],
    *,
    warmup_messages: int,
    timed_messages: int,
) -> None:
    """Wire size and msg/s + MB/s must match ``benchmark_kafka_case`` definitions."""

    value_bytes = int(row["value_bytes"])
    assert value_bytes > 0

    produce = row["produce"]
    consume = row["consume"]
    assert produce["messages"] == timed_messages
    assert consume["messages_read"] == warmup_messages + timed_messages

    wall_p = float(produce["wall_s"])
    wall_c = float(consume["wall_s"])
    assert wall_p > 0 and wall_c > 0

    total_read = float(warmup_messages + timed_messages)
    timed_f = float(timed_messages)
    checks: tuple[tuple[dict[str, Any], float, float], ...] = (
        (produce, timed_f, wall_p),
        (consume, total_read, wall_c),
    )
    for bucket, msg_count, wall in checks:
        tps = float(bucket["throughput_messages_per_s"])
        tmbs = float(bucket["throughput_megabytes_per_s"])
        mpm = float(bucket["mean_per_message_s"])
        assert tps == tps and tmbs == tmbs and mpm == mpm
        assert tps > 0 and tmbs > 0 and mpm > 0
        assert math.isclose(tps, msg_count / wall, rel_tol=1e-4, abs_tol=1e-9)
        assert math.isclose(
            tmbs,
            (value_bytes * msg_count / wall) / (1024.0 * 1024.0),
            rel_tol=1e-4,
            abs_tol=1e-12,
        )
        assert math.isclose(mpm, wall / msg_count, rel_tol=1e-4, abs_tol=1e-12)


@pytest.mark.kafka
@pytest.mark.distributed
def test_kafka_publish_consume_large_payload_all_codecs(
    kafka_bootstrap_servers: str,
    tmp_path: Path,
) -> None:
    """End-to-end produce/consume for each codec; attach ``kafka_e2e`` to a report."""

    profile = PayloadProfile.large
    event = sample_event(profile, seed=42)
    cases: list[dict[str, Any]] = []
    for fmt in ("json", "avro", "protobuf"):
        codec = codec_for_profile(fmt, profile)
        row = benchmark_kafka_case(
            bootstrap_servers=kafka_bootstrap_servers,
            codec=fmt,
            payload_profile=profile.value,
            serialize=_serialize_factory(codec, event),
            warmup_messages=5,
            timed_messages=15,
            deserialize=codec.decode,
        )
        assert row["produce"]["messages"] == 15
        _assert_kafka_e2e_size_and_throughput(
            row,
            warmup_messages=5,
            timed_messages=15,
        )
        des = row.get("deserialize")
        assert isinstance(des, dict)
        assert float(des["mean_s"]) > 0
        cases.append(row)

    by_codec = {str(c["codec"]): c for c in cases}
    vb_json = int(by_codec["json"]["value_bytes"])
    assert vb_json >= int(by_codec["avro"]["value_bytes"])
    assert vb_json >= int(by_codec["protobuf"]["value_bytes"])

    broker = os.environ.get("KSP_KAFKA_BROKER_LABEL", "kafka_protocol")
    block = build_kafka_e2e_block(
        bootstrap_servers=kafka_bootstrap_servers,
        broker_implementation=broker,
        cases=cases,
    )
    assert block["kafka_e2e_version"] == 2
    assert "producer_config" in block
    for c in block["cases"]:
        _assert_kafka_e2e_size_and_throughput(
            c,
            warmup_messages=5,
            timed_messages=15,
        )
    assert len(block["cases"]) == 3

    report: dict[str, Any] = {
        "report_version": 9,
        "scenario": {
            "tier": "S0",
            "payload_profiles": [profile.value],
            "formats": ["json", "avro", "protobuf"],
        },
        "results": [],
    }
    attach_kafka_e2e_to_report(report, block)
    assert "kafka_e2e" in report
    assert report["scenario"]["integrations"] == ["kafka_e2e"]

    out = tmp_path / "with_kafka.json"
    out.write_text(json.dumps(report), encoding="utf-8")
    loaded = cast(dict[str, Any], json.loads(out.read_text(encoding="utf-8")))
    assert loaded["kafka_e2e"]["cases"][0]["codec"] == "json"


@pytest.mark.kafka
def test_kafka_case_json_small_payload_smoke(kafka_bootstrap_servers: str) -> None:
    """Minimal traffic against the broker (small payload)."""

    profile = PayloadProfile.small
    event = sample_event(profile, seed=1)
    codec = codec_for_profile("json", profile)
    row = benchmark_kafka_case(
        bootstrap_servers=kafka_bootstrap_servers,
        codec="json",
        payload_profile=profile.value,
        serialize=_serialize_factory(codec, event),
        warmup_messages=2,
        timed_messages=5,
        deserialize=codec.decode,
    )
    assert row["serialize"]["mean_s"] > 0
    assert isinstance(row.get("deserialize"), dict)
    _assert_kafka_e2e_size_and_throughput(
        row,
        warmup_messages=2,
        timed_messages=5,
    )
