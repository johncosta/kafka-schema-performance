from __future__ import annotations

import json
from pathlib import Path

from benchmark.report.limitations import limitations_for_report
from benchmark.viz.summary_html import build_summary_html, write_summary_visualization


def _row(
    *,
    tier: str,
    profile: str,
    codec: str,
    enc: float,
    dec: float,
    rt: float,
    raw: int = 100,
) -> dict[str, object]:
    return {
        "payload_profile": profile,
        "codec": codec,
        "tier": tier,
        "raw_size_bytes": raw,
        "encode": {"mean_s": enc},
        "decode": {"mean_s": dec},
        "round_trip": {"mean_s": rt},
    }


def test_build_summary_html_stack_data_link_when_href_set() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json", "avro"],
            "compression": "zstd",
            "timed_iterations": 10,
        },
        "results": [
            _row(tier="S0", profile="small", codec="json", enc=2e-6, dec=2e-6, rt=2e-6),
            _row(tier="S0", profile="small", codec="avro", enc=1e-6, dec=1e-6, rt=1e-6),
        ],
    }
    html = build_summary_html(report, companion_stack_href="stack.html")
    assert 'class="page-nav"' in html
    assert 'href="stack.html"' in html
    assert "Stack &amp; component times" in html
    assert 'href="stack.html">stack &amp; data view</a>' in html


def test_build_summary_html_win_rate_percentages() -> None:
    report = {
        "report_version": 9,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["avro", "json"],
            "compression": "zstd",
            "timed_iterations": 10,
        },
        "results": [
            _row(
                tier="S0",
                profile="small",
                codec="json",
                enc=5e-6,
                dec=5e-6,
                rt=5e-6,
                raw=200,
            ),
            _row(
                tier="S0",
                profile="small",
                codec="avro",
                enc=1e-6,
                dec=1e-6,
                rt=1e-6,
                raw=90,
            ),
        ],
    }
    html = build_summary_html(report)
    assert "Win rate across comparisons" in html
    # Encode, decode, round-trip, raw wire → 4 wins for avro (no ties).
    assert "<strong>100.0%</strong>" in html
    assert "% of comparisons" in html


def test_build_summary_html_win_rate_no_head_to_head() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 3,
        },
        "results": [
            _row(tier="S0", profile="small", codec="json", enc=1e-6, dec=1e-6, rt=1e-6),
        ],
    }
    html = build_summary_html(report)
    assert "No head-to-head comparisons" in html


def test_build_summary_html_headlines_when_spread_large() -> None:
    report = {
        "report_version": 9,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["avro", "protobuf", "json"],
            "compression": "zstd",
            "timed_iterations": 10,
        },
        "results": [
            _row(tier="S0", profile="small", codec="json", enc=3e-6, dec=3e-6, rt=5e-6),
            _row(tier="S0", profile="small", codec="avro", enc=1e-6, dec=1e-6, rt=1e-6),
            _row(
                tier="S0",
                profile="small",
                codec="protobuf",
                enc=1.5e-6,
                dec=1.5e-6,
                rt=1.2e-6,
            ),
        ],
    }
    html = build_summary_html(report)
    assert "Performance summary" in html
    assert "Headlines" in html
    assert "S0 round-trip" in html
    assert "avro" in html
    assert "json" in html
    assert "matrix" in html
    assert "best" in html.lower()


def test_build_summary_html_highlights_best_encode_column() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json", "avro"],
            "compression": "zstd",
            "timed_iterations": 5,
        },
        "results": [
            _row(tier="S0", profile="small", codec="json", enc=2e-6, dec=2e-6, rt=2e-6),
            _row(tier="S0", profile="small", codec="avro", enc=1e-6, dec=2e-6, rt=2e-6),
        ],
    }
    html = build_summary_html(report)
    assert 'class="best"' in html


def test_build_summary_html_limitations_include_evidence_gaps() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 3,
        },
        "results": [
            _row(tier="S0", profile="small", codec="json", enc=1e-6, dec=1e-6, rt=1e-6),
        ],
        "limitations": limitations_for_report(),
    }
    html = build_summary_html(report)
    assert "not measured here" in html.lower()


def test_build_summary_html_regression_and_limitations() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 3,
        },
        "results": [
            _row(tier="S0", profile="small", codec="json", enc=1e-6, dec=1e-6, rt=1e-6),
        ],
        "regression_check": {
            "skipped": False,
            "warnings": [{"message": "round_trip regressed vs baseline"}],
        },
        "limitations": {
            "summary": "Micro-benchmark caveats.",
            "interpretation_policy": "Do not overfit.",
            "points": ["Point A", "Point B"],
        },
    }
    html = build_summary_html(report)
    assert "Regression hints" in html
    assert "round_trip regressed" in html
    assert "Micro-benchmark caveats" in html
    assert "Do not overfit" in html
    assert "Point A" in html


def test_write_summary_visualization_round_trip(tmp_path: Path) -> None:
    jp = tmp_path / "report.json"
    op = tmp_path / "out" / "summary.html"
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
            _row(tier="S0", profile="small", codec="json", enc=1e-6, dec=1e-6, rt=1e-6),
        ],
    }
    jp.write_text(json.dumps(report), encoding="utf-8")
    write_summary_visualization(jp, op)
    assert op.is_file()
    assert "Performance summary" in op.read_text(encoding="utf-8")


def test_build_summary_html_includes_kafka_e2e_section() -> None:
    report = {
        "report_version": 9,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 1,
        },
        "results": [
            _row(tier="S0", profile="small", codec="json", enc=1e-6, dec=1e-6, rt=1e-6),
        ],
        "kafka_e2e": {
            "kafka_e2e_version": 1,
            "broker_implementation": "test",
            "bootstrap_servers": "127.0.0.1:19092",
            "phases": {"produce": "sync send"},
            "cases": [
                {
                    "codec": "json",
                    "payload_profile": "small",
                    "value_bytes": 10,
                    "serialize": {"mean_s": 1e-7},
                    "produce": {"mean_per_message_s": 1e-4},
                    "consume": {"mean_per_message_s": 2e-4},
                },
            ],
        },
    }
    html = build_summary_html(report)
    assert "Kafka-protocol end-to-end" in html
    assert "127.0.0.1:19092" in html


def test_build_summary_html_includes_test_suite_ai_handoff() -> None:
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
            _row(tier="S0", profile="small", codec="json", enc=1e-6, dec=1e-6, rt=1e-6),
        ],
    }
    html = build_summary_html(report)
    assert "Test suite (for external review)" in html
    assert "gap analysis" in html
    assert "pytest inventory" in html
    assert "test_distributed_performance.py" in html
    assert "test_kafka_distributed.py" in html
    assert 'class="ai-handoff-pre"' in html
