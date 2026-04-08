from __future__ import annotations

from pathlib import Path

from benchmark.generate.records import PayloadProfile
from benchmark.report.render import render_markdown
from benchmark.scenarios.runner import build_report, embed_rubric

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_embed_rubric_pins_ref_and_criteria() -> None:
    p = _REPO_ROOT / "rubrics" / "governance.v1.yaml"
    e = embed_rubric(str(p))
    assert e["rubric_ref"] == "governance.v1"
    assert e["source_file"] == "governance.v1.yaml"
    ids = {c["id"] for c in e["criteria"]}
    assert "registry_coupling" in ids
    assert all("evidence_prompt" in c for c in e["criteria"])


def test_governance_weights_sum_to_weight_max() -> None:
    e = embed_rubric(str(_REPO_ROOT / "rubrics" / "governance.v1.yaml"))
    total = sum(int(c["weight"]) for c in e["criteria"])
    assert total == int(e["weight_max"])


def test_maintainability_weights_sum_to_weight_max() -> None:
    e = embed_rubric(str(_REPO_ROOT / "rubrics" / "maintainability.v1.yaml"))
    total = sum(int(c["weight"]) for c in e["criteria"])
    assert total == int(e["weight_max"])


def test_build_report_rubric_index_and_markdown_appendix() -> None:
    gov = _REPO_ROOT / "rubrics" / "governance.v1.yaml"
    maint = _REPO_ROOT / "rubrics" / "maintainability.v1.yaml"
    report = build_report(
        profiles=[PayloadProfile.small],
        tier="S0",
        formats=["json"],
        compression="zstd",
        warmup=0,
        iterations=1,
        seed=0,
        rubric_governance=str(gov),
        rubric_maintainability=str(maint),
    )
    assert report["rubric_index"] == ["governance.v1", "maintainability.v1"]
    md = render_markdown(report)
    assert "## Appendix: Rubrics" in md
    assert "Evidence prompts" in md
    assert "`governance.v1`" in md
    assert "`maintainability.v1`" in md
