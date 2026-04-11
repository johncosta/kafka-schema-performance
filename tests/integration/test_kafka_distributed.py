"""Containerized Kafka-protocol benchmarks; merge metrics into report shape."""

from __future__ import annotations

import json
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
        )
        assert row["produce"]["messages"] == 15
        assert row["value_bytes"] > 0
        assert row["produce"]["wall_s"] > 0
        assert row["consume"]["wall_s"] > 0
        cases.append(row)

    broker = os.environ.get("KSP_KAFKA_BROKER_LABEL", "kafka_protocol")
    block = build_kafka_e2e_block(
        bootstrap_servers=kafka_bootstrap_servers,
        broker_implementation=broker,
        cases=cases,
    )
    assert block["kafka_e2e_version"] == 2
    assert "producer_config" in block
    assert "throughput_megabytes_per_s" in block["cases"][0]["produce"]
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
    )
    assert row["serialize"]["mean_s"] > 0
