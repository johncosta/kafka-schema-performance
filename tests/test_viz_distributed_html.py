from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from benchmark.metrics.compress import CompressionAlg
from benchmark.scenarios.runner import PayloadProfile, ReportTier, build_report
from benchmark.viz.distributed_html import (
    build_distributed_html,
    write_distributed_visualization,
)


def test_build_distributed_html_from_distributed_style_report() -> None:
    """Same ``build_report`` shape as ``tests/test_distributed_performance.py``."""

    report = build_report(
        profiles=[PayloadProfile.large],
        tier=cast(ReportTier, "S1"),
        formats=["avro", "protobuf", "json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=0,
        iterations=2,
        seed=42,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    html = build_distributed_html(
        report,
        companion_stack_href="stack.html",
        companion_summary_href="summary.html",
    )
    assert "Distributed footprint" in html
    assert "test_distributed_performance.py" in html
    assert "S1 — timed compressed payload" in html
    assert "Compressed bytes" in html
    assert 'href="stack.html"' in html
    assert 'href="summary.html"' in html
    assert "Profile: large" in html


def test_build_distributed_html_highlights_smallest_raw() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json", "avro"],
            "compression": "zstd",
            "timed_iterations": 3,
        },
        "results": [
            {
                "payload_profile": "small",
                "codec": "json",
                "tier": "S0",
                "raw_size_bytes": 500,
                "encode": {"mean_s": 1e-6},
                "decode": {"mean_s": 1e-6},
                "round_trip": {"mean_s": 2e-6},
            },
            {
                "payload_profile": "small",
                "codec": "avro",
                "tier": "S0",
                "raw_size_bytes": 100,
                "encode": {"mean_s": 1e-6},
                "decode": {"mean_s": 1e-6},
                "round_trip": {"mean_s": 2e-6},
            },
        ],
    }
    html = build_distributed_html(report)
    assert 'class="num best">100' in html


def test_write_distributed_visualization_roundtrip(tmp_path: Path) -> None:
    jp = tmp_path / "report.json"
    stack = tmp_path / "stack.html"
    summary = tmp_path / "summary.html"
    dist = tmp_path / "out" / "distributed.html"
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 1,
        },
        "results": [
            {
                "payload_profile": "small",
                "codec": "json",
                "tier": "S0",
                "raw_size_bytes": 10,
                "encode": {"mean_s": 1e-6},
                "decode": {"mean_s": 1e-6},
                "round_trip": {"mean_s": 2e-6},
            },
        ],
    }
    jp.write_text(json.dumps(report), encoding="utf-8")
    write_distributed_visualization(
        jp,
        dist,
        companion_stack_path=stack,
        companion_summary_path=summary,
    )
    assert dist.is_file()
    text = dist.read_text(encoding="utf-8")
    assert "Distributed footprint" in text
    assert "../stack.html" in text
    assert "../summary.html" in text
