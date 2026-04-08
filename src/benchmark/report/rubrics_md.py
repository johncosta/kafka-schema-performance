from __future__ import annotations

from typing import Any


def _criteria_rows(rubric: dict[str, Any]) -> list[dict[str, Any]]:
    crit = rubric.get("criteria")
    if not isinstance(crit, list):
        return []
    rows = []
    for item in crit:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def append_rubric_appendix(lines: list[str], report: dict[str, Any]) -> None:
    """Phase 4: human-scored rubrics in Markdown (weights + evidence prompts)."""

    idx = report.get("rubric_index")
    if not idx:
        return

    lines.append("## Appendix: Rubrics (governance and maintainability)")
    lines.append("")
    lines.append(
        "Scores are **human- or process-assigned**; this harness does not infer "
        "rubric points from benchmark timings."
    )
    lines.append("")
    lines.append(f"**Rubric references in this report:** `{', '.join(idx)}`")
    lines.append("")

    pairs = [
        ("governance_rubric", "Governance scorecard"),
        ("maintainability_rubric", "Maintainability rubric"),
    ]
    for key, heading in pairs:
        block = report.get(key)
        if not isinstance(block, dict):
            continue
        ref = block.get("rubric_ref", key)
        title = block.get("title", heading)
        ver = block.get("version", "?")
        src = block.get("source_file", "")
        lines.append(f"### {heading} (`{ref}`)")
        lines.append("")
        lines.append(f"- **Title:** {title}")
        lines.append(f"- **YAML version:** {ver}")
        if src:
            lines.append(f"- **Source file:** `{src}`")
        wmax = block.get("weight_max")
        scale = block.get("scale")
        if wmax is not None:
            lines.append(
                f"- **Weight model:** criteria weights sum to **{wmax}**.",
            )
        if scale is not None:
            lines.append(f"- **Score scale:** {scale}")
        lines.append("")
        lines.append("| Criterion ID | Weight | Score | Label |")
        lines.append("|--------------|--------|-------|-------|")
        total_w = 0
        for c in _criteria_rows(block):
            cid = str(c.get("id", ""))
            w = c.get("weight", "")
            if isinstance(w, (int, float)):
                total_w += int(w)
            score = c.get("score", "—")
            if score is None:
                score = "—"
            label = str(c.get("label", "")).replace("|", "\\|")
            lines.append(f"| `{cid}` | {w} | {score} | {label} |")
        if total_w:
            lines.append("")
            lines.append(f"*Sum of listed weights:* **{total_w}**")
        lines.append("")
        for c in _criteria_rows(block):
            cid = str(c.get("id", ""))
            prompt = c.get("evidence_prompt")
            if not prompt:
                continue
            lines.append(f"#### Evidence prompts: `{cid}`")
            lines.append("")
            for para in str(prompt).strip().split("\n\n"):
                lines.append(para.strip())
                lines.append("")
            notes = c.get("notes")
            if notes:
                lines.append(f"*Notes:* {notes}")
                lines.append("")
