from __future__ import annotations

import json
from pathlib import Path

from benchmark.viz.summary_html import (
    aggregate_codec_win_rates,
    build_summary_html,
    group_rows_for_win_rate,
)

_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "reports"
    / "golden_two_codecs.report.json"
)


def test_golden_report_json_win_rate_matches_hand_check() -> None:
    """PRD §6.6.7: canned report → deterministic win-rate totals."""

    report = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    rows = report["results"]
    assert isinstance(rows, list)
    groups = group_rows_for_win_rate(rows)
    n, win_pts, order = aggregate_codec_win_rates(groups, rows)
    assert n == 4
    assert win_pts["avro"] == 4.0
    assert win_pts["json"] == 0.0
    assert order[0] == "avro"


def test_golden_report_summary_html_renders_win_section() -> None:
    report = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    html = build_summary_html(report)
    assert "Win rate across comparisons" in html
    assert "<strong>100.0%</strong>" in html


def test_aggregate_codec_win_rate_tie_splits_evenly() -> None:
    rows = [
        {
            "payload_profile": "small",
            "codec": "json",
            "tier": "S0",
            "raw_size_bytes": 100,
            "encode": {"mean_s": 2e-6},
            "decode": {"mean_s": 1e-6},
            "round_trip": {"mean_s": 1e-6},
        },
        {
            "payload_profile": "small",
            "codec": "avro",
            "tier": "S0",
            "raw_size_bytes": 200,
            "encode": {"mean_s": 2e-6},
            "decode": {"mean_s": 3e-6},
            "round_trip": {"mean_s": 3e-6},
        },
    ]
    groups = group_rows_for_win_rate(rows)
    n, win_pts, _order = aggregate_codec_win_rates(groups, rows)
    assert n == 4
    assert win_pts["json"] == 3.5
    assert win_pts["avro"] == 0.5
