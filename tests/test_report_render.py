from __future__ import annotations

from typing import cast

from benchmark.generate.records import PayloadProfile
from benchmark.integration.kafka_e2e import (
    attach_kafka_e2e_to_report,
    build_kafka_e2e_block,
)
from benchmark.metrics.compress import CompressionAlg
from benchmark.report.render import render_markdown
from benchmark.scenarios.runner import ReportTier, build_report


def test_render_markdown_multi_profile_headings() -> None:
    report = build_report(
        profiles=[PayloadProfile.small, PayloadProfile.medium],
        tier="S0",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=1,
        seed=0,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    md = render_markdown(report)
    assert "### Profile `small`" in md
    assert "### Profile `medium`" in md
    assert "Round-trip:" in md
    assert "Measurement model" in md
    assert "Raw encoded size" in md
    assert "Compressed payload sizes" in md
    assert "## Limitations" in md
    assert "## Artifact integrity" in md
    assert "### Evidence coverage (PRD §6.6)" in md
    assert "Not measured (do not infer from this report alone)" in md


def test_render_markdown_s3_tier_section() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S3",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=1,
        seed=0,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=8,
    )
    md = render_markdown(report)
    assert "### Tier S3 (memory producer batch)" in md
    assert "S3 producer batch (memory, no broker)" in md
    assert "**Batch size:** 8" in md


def test_render_markdown_tier_all_includes_tiers_executed_and_tier_sections() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier=cast(ReportTier, "all"),
        formats=["json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=0,
        iterations=1,
        seed=0,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=4,
    )
    md = render_markdown(report)
    assert "Tiers executed (single report)" in md
    assert "### Tier S1 (codec + compression)" in md
    assert "### Tier S2 (codec + mock schema registry)" in md
    assert "#### json — `S0`" in md
    assert "#### json — `S4`" in md


def test_render_markdown_s1_tier_section() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S1",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=1,
        seed=0,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    md = render_markdown(report)
    assert "### Tier S1 (codec + compression)" in md
    assert "S1 compression footprint" in md
    assert "S1 phase isolation (PRD §6.6.1)" in md
    assert "Compress wire only" in md


def test_render_markdown_includes_kafka_e2e_section() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S0",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=1,
        seed=0,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    block = build_kafka_e2e_block(
        bootstrap_servers="127.0.0.1:19092",
        broker_implementation="fixture",
        cases=[
            {
                "codec": "json",
                "payload_profile": "small",
                "value_bytes": 100,
                "warmup_messages": 1,
                "timed_messages": 5,
                "serialize": {"iterations": 20, "mean_s": 1e-6, "note": "n"},
                "deserialize": {
                    "iterations": 20,
                    "mean_s": 2e-6,
                    "note": "In-process decode.",
                },
                "produce": {
                    "messages": 5,
                    "wall_s": 0.01,
                    "mean_per_message_s": 0.002,
                    "throughput_messages_per_s": 500.0,
                    "throughput_megabytes_per_s": 0.05,
                },
                "consume": {
                    "messages_read": 6,
                    "wall_s": 0.02,
                    "mean_per_message_s": 0.003,
                    "throughput_messages_per_s": 300.0,
                    "throughput_megabytes_per_s": 0.03,
                    "note": "n",
                },
            },
        ],
    )
    attach_kafka_e2e_to_report(report, block)
    md = render_markdown(report)
    assert "## Kafka-protocol end-to-end" in md
    assert "kafka_e2e_version:** 2" in md
    assert "Timed produce:" in md
    assert "MB/s" in md
    assert "Producer config (snapshot)" in md
    assert "Deserialize mean (same value bytes, not in consumer poll)" in md
