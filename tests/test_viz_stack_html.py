from __future__ import annotations

from pathlib import Path

from benchmark.viz.stack_html import build_stack_html, write_stack_visualization


def test_build_stack_html_includes_encode_decode_bars() -> None:
    report = {
        "report_version": 7,
        "scenario": {
            "tier": "S0",
            "payload_profiles": ["small"],
            "timed_iterations": 10,
        },
        "results": [
            {
                "payload_profile": "small",
                "codec": "json",
                "tier": "S0",
                "raw_size_bytes": 200,
                "encode": {"mean_s": 1e-6},
                "decode": {"mean_s": 2e-6},
                "round_trip": {"mean_s": 3e-6},
            },
        ],
    }
    html = build_stack_html(report)
    assert "Encode (timed window)" in html
    assert "Decode (timed window)" in html
    assert "Round-trip (single timer)" in html
    assert "json" in html
    assert "S0" in html


def test_build_stack_html_s2_registry_bars() -> None:
    report = {
        "report_version": 7,
        "scenario": {
            "tier": "S2",
            "payload_profiles": ["small"],
            "timed_iterations": 3,
        },
        "results": [
            {
                "payload_profile": "small",
                "codec": "json",
                "tier": "S2",
                "raw_size_bytes": 100,
                "encode": {"mean_s": 5e-6},
                "decode": {"mean_s": 4e-6},
                "round_trip": {"mean_s": 9e-6},
                "s2_registry": {
                    "fetch_new_tcp_each_iteration": {"mean_s": 1e-4},
                    "fetch_reused_connection": {"mean_s": 2e-5},
                },
            },
        ],
    }
    html = build_stack_html(report)
    assert "S2: registry GET (new TCP each)" in html
    assert "S2: registry GET (keep-alive)" in html


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
    assert "Round-trip" in out.read_text(encoding="utf-8")
