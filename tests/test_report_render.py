from __future__ import annotations

from benchmark.generate.records import PayloadProfile
from benchmark.report.render import render_markdown
from benchmark.scenarios.runner import build_report


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
