from __future__ import annotations

from typing import cast

from benchmark.generate.records import PayloadProfile
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
