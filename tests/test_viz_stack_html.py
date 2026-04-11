from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from benchmark.generate.records import PayloadProfile
from benchmark.metrics.compress import CompressionAlg
from benchmark.scenarios.runner import ReportTier, ScenarioTier, build_report
from benchmark.viz.distributed_html import write_distributed_visualization
from benchmark.viz.stack_html import (
    TIER_DESCRIPTIONS,
    TIER_ORDER,
    build_stack_html,
    write_stack_visualization,
)
from benchmark.viz.summary_html import write_summary_visualization


def _minimal_row(
    *,
    tier: str,
    profile: str,
    codec: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    base: dict[str, object] = {
        "payload_profile": profile,
        "codec": codec,
        "tier": tier,
        "raw_size_bytes": 100,
        "encode": {"mean_s": 1e-6},
        "decode": {"mean_s": 2e-6},
        "round_trip": {"mean_s": 3e-6},
    }
    if extra:
        base.update(extra)
    return base


def test_tier_constants_cover_all_ordered_tiers() -> None:
    assert set(TIER_ORDER) == set(TIER_DESCRIPTIONS.keys())


def test_build_stack_html_glossary_lists_all_tiers() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 10,
        },
        "results": [_minimal_row(tier="S0", profile="small", codec="json")],
    }
    html = build_stack_html(report)
    assert "What do benchmark tiers mean?" in html
    for t in TIER_ORDER:
        assert f"<strong>{t}</strong></dt>" in html
        assert TIER_DESCRIPTIONS[t][:30] in html


def test_build_stack_html_includes_encode_decode_bars() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 10,
        },
        "results": [
            {
                **_minimal_row(tier="S0", profile="small", codec="json"),
                "raw_size_bytes": 200,
                "compressed_payload_bytes": {
                    "gzip": {"bytes": 120, "compresslevel": 6},
                    "zstd": {"bytes": 110, "level": 3},
                },
            },
        ],
    }
    html = build_stack_html(report)
    assert "data-tab-group" in html
    for t in TIER_ORDER:
        assert f'id="tiertab-{t.lower()}"' in html
        assert f'id="tierpanel-{t.lower()}"' in html
    assert 'class="tab tab-active" role="tab" id="tiertab-s0"' in html
    assert '<p class="empty-tier">' in html
    assert html.count('<p class="empty-tier">') == 4
    assert 'id="tierpanel-s0"' in html
    assert "tier-desc" in html
    assert "Codec only" in html
    assert "Encode (timed window)" in html
    assert "Decode (timed window)" in html
    assert "Round-trip (single timer)" in html
    assert "json" in html
    assert "Scenario tier:" in html
    assert "<strong>Formats:</strong> json" in html
    assert "<strong>Compression (scenario / S1 timed):</strong> zstd" in html
    assert "Phase-3 size probes" in html
    assert "gzip</strong> 120" in html
    assert "zstd</strong> 110" in html
    assert "Width scale is shared" in html


def test_build_stack_html_s2_registry_bars() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S2",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "gzip",
            "timed_iterations": 3,
        },
        "results": [
            {
                **_minimal_row(tier="S2", profile="small", codec="json"),
                "s2_registry": {
                    "fetch_new_tcp_each_iteration": {"mean_s": 1e-4},
                    "fetch_reused_connection": {"mean_s": 2e-5},
                },
            },
        ],
    }
    html = build_stack_html(report)
    assert 'class="tab tab-active" role="tab" id="tiertab-s2"' in html
    assert 'id="tierpanel-s2"' in html
    assert "empty-tier" in html
    assert "loopback mock Confluent-style schema registry" in html
    assert "S2: registry GET (new TCP each)" in html
    assert "S2: registry GET (keep-alive)" in html


def test_build_stack_html_s1_shows_timed_compression_meta() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S1",
            "payload_profiles": ["small"],
            "formats": ["avro", "protobuf", "json"],
            "compression": "gzip",
            "timed_iterations": 2,
        },
        "results": [
            {
                **_minimal_row(tier="S1", profile="small", codec="json"),
                "compression": "gzip",
                "raw_size_bytes": 500,
                "compressed_size_bytes": 200,
                "compressed_payload_bytes": {
                    "gzip": {"bytes": 180, "compresslevel": 6},
                    "zstd": {"bytes": 170, "level": 3},
                },
            },
        ],
    }
    html = build_stack_html(report)
    assert 'class="tab tab-active" role="tab" id="tiertab-s1"' in html
    assert 'id="tierpanel-s1"' in html
    assert "Codec plus timed compression" in html
    assert "S1 timed wire" in html
    assert "gzip</strong>): <strong>200</strong>" in html
    assert "Phase-3 size probes" in html


def test_build_stack_html_s3_s4_bars() -> None:
    s3 = {
        **_minimal_row(tier="S3", profile="small", codec="json"),
        "s3_producer_batch": {
            "batch_size": 8,
            "batch_build_and_join": {"mean_s": 1e-5},
        },
    }
    s4 = {
        **_minimal_row(tier="S4", profile="small", codec="json"),
        "s4_consumer_batch": {
            "batch_size": 8,
            "batch_decode": {"mean_s": 2e-5},
        },
    }
    html3 = build_stack_html(
        {
            "report_version": 8,
            "scenario": {
                "tier": "S3",
                "payload_profiles": ["small"],
                "formats": ["json"],
                "compression": "zstd",
                "timed_iterations": 1,
            },
            "results": [s3],
        },
    )
    assert 'class="tab tab-active" role="tab" id="tiertab-s3"' in html3
    assert 'id="tierpanel-s3"' in html3
    assert "producer-style batch" in html3
    assert "S3: producer batch" in html3

    html4 = build_stack_html(
        {
            "report_version": 8,
            "scenario": {
                "tier": "S4",
                "payload_profiles": ["small"],
                "formats": ["json"],
                "compression": "zstd",
                "timed_iterations": 1,
            },
            "results": [s4],
        },
    )
    assert 'class="tab tab-active" role="tab" id="tiertab-s4"' in html4
    assert 'id="tierpanel-s4"' in html4
    assert "consumer-style batch" in html4
    assert "S4: consumer batch decode" in html4


def test_build_stack_html_mixed_row_tiers_two_top_tabs() -> None:
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
            _minimal_row(tier="S0", profile="small", codec="json"),
            {
                **_minimal_row(tier="S1", profile="small", codec="json"),
                "compression": "zstd",
                "compressed_size_bytes": 50,
                "compressed_payload_bytes": {
                    "gzip": {"bytes": 40, "compresslevel": 6},
                    "zstd": {"bytes": 35, "level": 3},
                },
            },
        ],
    }
    html = build_stack_html(report)
    for t in TIER_ORDER:
        assert f'id="tiertab-{t.lower()}"' in html
    assert 'class="tab tab-active" role="tab" id="tiertab-s0"' in html
    assert 'id="tierpanel-s0"' in html
    assert 'id="tierpanel-s1"' in html


def test_build_stack_html_full_matrix_sections() -> None:
    """All payload profiles × all codecs appear as separate sections under S0."""

    profiles = ["small", "medium", "large", "map_heavy", "evolution"]
    codecs = ["avro", "protobuf", "json"]
    rows: list[dict[str, object]] = []
    for p in profiles:
        for c in codecs:
            rows.append(
                {
                    **_minimal_row(tier="S0", profile=p, codec=c),
                    "raw_size_bytes": 10,
                    "compressed_payload_bytes": {
                        "gzip": {"bytes": 9, "compresslevel": 6},
                        "zstd": {"bytes": 8, "level": 3},
                    },
                },
            )
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": profiles,
            "formats": codecs,
            "compression": "zstd",
            "timed_iterations": 1,
        },
        "results": rows,
    }
    html = build_stack_html(report)
    assert html.count('<section class="result">') == 15
    assert html.count('role="tabpanel"') == 10
    assert html.count('data-tab-target="prof-s0-panel-') == 5
    assert 'id="prof-s0-panel-small"' in html
    assert 'id="prof-s0-panel-map-heavy"' in html
    assert 'id="prof-s0-panel-evolution"' in html
    for c in codecs:
        assert f"<code>{c}</code>" in html
    assert "avro, protobuf, json" in html


_TIER_VIZ_NEEDLES: dict[str, str] = {
    "S0": "Encode (timed window)",
    "S1": "S1 timed wire",
    "S2": "S2: registry GET (new TCP each)",
    "S3": "S3: producer batch",
    "S4": "S4: consumer batch decode",
}


@pytest.mark.parametrize("tier", ["S0", "S1", "S2", "S3", "S4"])
@pytest.mark.parametrize("compression", ["gzip", "zstd"])
def test_build_stack_html_from_build_report_each_tier_and_compression(
    tier: str,
    compression: str,
) -> None:
    """Real report for every tier × scenario compression (smoke JSON row)."""

    comp = cast(CompressionAlg, compression)
    report = build_report(
        profiles=[PayloadProfile.small],
        tier=cast(ScenarioTier, tier),
        formats=["json"],
        compression=comp,
        warmup=0,
        iterations=1,
        seed=11,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=4,
    )
    html = build_stack_html(report)
    assert _TIER_VIZ_NEEDLES[tier] in html
    assert f'class="tab tab-active" role="tab" id="tiertab-{tier.lower()}"' in html
    assert f'id="tierpanel-{tier.lower()}"' in html
    assert "What do benchmark tiers mean?" in html
    assert f"<strong>Compression (scenario / S1 timed):</strong> {compression}" in html


def test_build_stack_html_tier_all_no_empty_tier_placeholders() -> None:
    report = build_report(
        profiles=[PayloadProfile.small],
        tier=cast(ReportTier, "all"),
        formats=["json"],
        compression=cast(CompressionAlg, "zstd"),
        warmup=0,
        iterations=1,
        seed=7,
        rubric_governance=None,
        rubric_maintainability=None,
        batch_size=4,
    )
    html = build_stack_html(report)
    assert '<p class="empty-tier">' not in html
    assert "Scenario tier:" in html and "all" in html


def test_build_stack_html_from_build_report_full_matrix_avro_protobuf_json() -> None:
    """Viz over a full profile × format matrix (single tier / compression)."""

    report = build_report(
        profiles=list(PayloadProfile),
        tier="S0",
        formats=["avro", "protobuf", "json"],
        compression=cast(CompressionAlg, "gzip"),
        warmup=0,
        iterations=1,
        seed=19,
        rubric_governance=None,
        rubric_maintainability=None,
    )
    html = build_stack_html(report)
    assert html.count('<section class="result">') == 15
    assert 'class="tab tab-active" role="tab" id="tiertab-s0"' in html
    assert "avro, protobuf, json" in html


def test_build_stack_html_includes_companion_summary_link() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 10,
        },
        "results": [_minimal_row(tier="S0", profile="small", codec="json")],
    }
    html = build_stack_html(report, companion_summary_href="summary.html")
    assert 'class="page-nav"' in html
    assert 'href="summary.html"' in html
    assert "Performance summary" in html


def test_build_stack_html_includes_companion_distributed_link() -> None:
    report = {
        "report_version": 8,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "formats": ["json"],
            "compression": "zstd",
            "timed_iterations": 10,
        },
        "results": [_minimal_row(tier="S0", profile="small", codec="json")],
    }
    html = build_stack_html(
        report,
        companion_summary_href="summary.html",
        companion_distributed_href="distributed.html",
    )
    assert 'href="summary.html"' in html
    assert 'href="distributed.html"' in html
    assert "Distributed footprint" in html


def test_write_stack_visualization_roundtrip(tmp_path: Path) -> None:
    src = tmp_path / "report.json"
    src.write_text(
        '{"report_version":1,"scenario":{"tier":"S0","payload_profiles":["x"],'
        '"timed_iterations":1},"results":['
        '{"payload_profile":"x","codec":"json","tier":"S0","raw_size_bytes":1,'
        '"encode":{"mean_s":1e-9},"decode":{"mean_s":1e-9},"round_trip":{"mean_s":2e-9}}'
        "]}",
        encoding="utf-8",
    )
    out = tmp_path / "out.html"
    write_stack_visualization(src, out)
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "Round-trip" in text
    assert 'role="tablist"' in text
    assert "What do benchmark tiers mean?" in text


def test_write_stack_visualization_cross_link_paths(tmp_path: Path) -> None:
    src = tmp_path / "report.json"
    src.write_text(
        '{"report_version":1,"scenario":{"tier":"S0","payload_profiles":["x"],'
        '"timed_iterations":1},"results":['
        '{"payload_profile":"x","codec":"json","tier":"S0","raw_size_bytes":1,'
        '"encode":{"mean_s":1e-9},"decode":{"mean_s":1e-9},"round_trip":{"mean_s":2e-9}}'
        "]}",
        encoding="utf-8",
    )
    stack = tmp_path / "nested" / "stack.html"
    summary = tmp_path / "summary.html"
    distributed = tmp_path / "distributed.html"
    write_stack_visualization(
        src,
        stack,
        companion_summary_path=summary,
        companion_distributed_path=distributed,
    )
    write_summary_visualization(
        src,
        summary,
        companion_stack_path=stack,
        companion_distributed_path=distributed,
    )
    write_distributed_visualization(
        src,
        distributed,
        companion_stack_path=stack,
        companion_summary_path=summary,
    )
    stack_txt = stack.read_text(encoding="utf-8")
    summary_txt = summary.read_text(encoding="utf-8")
    dist_txt = distributed.read_text(encoding="utf-8")
    assert "../summary.html" in stack_txt
    assert "../distributed.html" in stack_txt
    assert 'href="nested/stack.html"' in summary_txt
    assert "distributed.html" in summary_txt
    assert "stack &amp; data view" in summary_txt
    assert "distributed footprint" in summary_txt
    assert 'href="nested/stack.html"' in dist_txt
    assert 'href="summary.html"' in dist_txt
