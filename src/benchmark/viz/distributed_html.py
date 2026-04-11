"""Distributed footprint HTML: S0 wire size and S1 timed compressed bytes.

Uses the same ``report.json`` rows as ``tests/test_distributed_performance.py``
(in-process ``build_report`` / harness tiers): raw serialized size (S0) and
producer-ish compressed payload size (S1). Optional ``kafka_e2e`` block mirrors
the summary page when a broker run was merged into the report.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast

from benchmark.viz.stack_html import (
    build_viz_sibling_nav_html,
    companion_viz_nav_html,
    relative_viz_href,
)
from benchmark.viz.summary_html import (
    _codec,
    _kafka_e2e_section,
    _mean_wire_bytes,
    _profile,
    _profile_order,
    _s1_timed_compressed_bytes,
    _tier,
)

_DISTRIBUTED_PAGE_CSS = """
<style>
body {
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  margin: 1.5rem;
  max-width: 56rem;
  color: #1a1a1a;
}
h1 { font-size: 1.35rem; }
h2 { font-size: 1.05rem; margin-top: 1.25rem; }
h3 { font-size: 0.95rem; margin-top: 0.75rem; color: #333; }
.meta { font-size: 0.9rem; line-height: 1.5; }
.footprint {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 0.75rem 1rem 1rem;
  margin-bottom: 1.25rem;
  background: #fafafa;
}
.matrix {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
  margin-top: 0.5rem;
}
.matrix th, .matrix td {
  border: 1px solid #ccc;
  padding: 0.35rem 0.5rem;
  text-align: left;
}
.matrix th { background: #e8eef5; }
.matrix td.best { background: #e6f4ea; font-weight: 600; }
.matrix td.num { font-variant-numeric: tabular-nums; text-align: right; }
.fineprint {
  font-size: 0.78rem;
  color: #444;
  margin: 0.75rem 0 0;
  line-height: 1.4;
}
.page-nav {
  margin: 0 0 0.75rem;
  font-size: 0.92rem;
}
.page-nav a { color: #1e5a8a; }
.page-nav a:focus-visible { outline: 2px solid #2d6a9f; outline-offset: 2px; }
.cfg-pre {
  font-size: 0.78rem;
  max-height: 14rem;
  overflow: auto;
  background: #fff;
  border: 1px solid #ddd;
  padding: 0.5rem;
  margin: 0.35rem 0;
}
.meta { font-size: 0.85rem; color: #444; }
</style>
""".strip()


def _sort_codec_rows(
    rows: list[dict[str, Any]],
    formats_order: list[str],
) -> list[dict[str, Any]]:
    idx = {c: i for i, c in enumerate(formats_order)}
    return sorted(rows, key=lambda r: (idx.get(_codec(r), 999), _codec(r)))


def _s0_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No S0 rows for this profile.</p>"
    pairs: list[tuple[str, float | None]] = []
    for row in rows:
        pairs.append((_codec(row), _mean_wire_bytes(row)))
    finite = [w for _, w in pairs if w is not None and w == w]
    best = min(finite) if finite else None
    head = (
        '<table class="matrix"><thead><tr>'
        '<th>Codec</th><th class="num">Raw bytes (mean)</th></tr></thead><tbody>'
    )
    body: list[str] = []
    for codec, w in pairs:
        is_best = (
            best is not None
            and w is not None
            and w == w
            and abs(float(w) - float(best)) < 1e-6
        )
        td_cls = "num best" if is_best else "num"
        if w is not None and w == w:
            disp = html.escape(f"{float(w):,.0f}")
        else:
            disp = "?"
        ce = html.escape(codec)
        body.append(
            f"<tr><td><code>{ce}</code></td>" f'<td class="{td_cls}">{disp}</td></tr>',
        )
    return head + "".join(body) + "</tbody></table>"


def _s1_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No S1 rows for this profile.</p>"
    pairs: list[tuple[str, int | None]] = []
    for row in rows:
        b = _s1_timed_compressed_bytes(row)
        pairs.append((_codec(row), b))
    finite = [b for _, b in pairs if b is not None]
    best = min(finite) if finite else None
    head = (
        '<table class="matrix"><thead><tr>'
        '<th>Codec</th><th class="num">Compressed bytes</th></tr></thead><tbody>'
    )
    body: list[str] = []
    for codec, b in pairs:
        is_best = best is not None and b is not None and b == best
        td_cls = "num best" if is_best else "num"
        disp = html.escape(str(b)) if b is not None else "?"
        ce = html.escape(codec)
        body.append(
            f"<tr><td><code>{ce}</code></td>" f'<td class="{td_cls}">{disp}</td></tr>',
        )
    return head + "".join(body) + "</tbody></table>"


def _footprint_body(
    rows: list[dict[str, Any]],
    scen_profiles: list[Any],
    formats_order: list[str],
    comp: Any,
) -> str:
    tiered = [r for r in rows if _tier(r) in ("S0", "S1")]
    if not tiered:
        return "<p>No S0 or S1 rows in this report.</p>"
    profiles = _profile_order(scen_profiles, tiered)
    comp_e = html.escape(str(comp)) if comp is not None else "?"
    parts: list[str] = []
    for prof in profiles:
        s0 = _sort_codec_rows(
            [r for r in rows if _tier(r) == "S0" and _profile(r) == prof],
            formats_order,
        )
        s1 = _sort_codec_rows(
            [r for r in rows if _tier(r) == "S1" and _profile(r) == prof],
            formats_order,
        )
        if not s0 and not s1:
            continue
        pe = html.escape(prof)
        inner: list[str] = []
        if s0:
            inner.append("<h3>S0 — raw serialized bytes</h3>")
            inner.append(_s0_table(s0))
        if s1:
            inner.append(
                f"<h3>S1 — timed compressed payload "
                f"(scenario compression: {comp_e})</h3>",
            )
            inner.append(_s1_table(s1))
        parts.append(
            f'<section class="footprint"><h2 id="p-{pe}">Profile: {pe}</h2>'
            f'{"".join(inner)}</section>',
        )
    if not parts:
        return "<p>No S0 or S1 rows in this report.</p>"
    return "".join(parts)


def build_distributed_html(
    report: dict[str, Any],
    *,
    companion_stack_href: str | None = None,
    companion_summary_href: str | None = None,
    viz_nav_html: str | None = None,
) -> str:
    scen = report.get("scenario")
    if not isinstance(scen, dict):
        scen = {}
    tier = html.escape(str(scen.get("tier", "?")))
    profiles = scen.get("payload_profiles", [])
    prof_txt = html.escape(", ".join(str(p) for p in profiles) if profiles else "?")
    fmt_list = scen.get("formats", [])
    formats_order = [str(x) for x in fmt_list] if isinstance(fmt_list, list) else []
    fmt_txt = html.escape(", ".join(formats_order) if formats_order else "?")
    comp = scen.get("compression")
    comp_txt = html.escape(str(comp)) if comp is not None else "?"
    iters = scen.get("timed_iterations", "?")
    ver = report.get("report_version", "?")

    raw_results = report.get("results", [])
    rows = [r for r in raw_results if isinstance(r, dict)]
    scen_profiles_raw = profiles if isinstance(profiles, list) else []
    scen_profiles = [p for p in scen_profiles_raw if p is not None]

    kafka_html = _kafka_e2e_section(report)
    footprint = _footprint_body(rows, scen_profiles, formats_order, comp)
    intro = (
        '<section class="intro"><p>'
        "These tables highlight <strong>serialized size on the wire (S0)</strong> and "
        "<strong>timed compressed payload size (S1)</strong>—the same dimensions "
        "checked by <code>tests/test_distributed_performance.py</code> "
        "(in-process harness; no broker). "
        "Smaller values are better for retention, replication, and producer bandwidth."
        "</p></section>"
    )
    body = kafka_html + intro + footprint

    meta = (
        f"<p><strong>Scenario tier:</strong> {tier} &nbsp;|&nbsp; "
        f"<strong>Profiles:</strong> {prof_txt} &nbsp;|&nbsp; "
        f"<strong>Formats:</strong> {fmt_txt} &nbsp;|&nbsp; "
        f"<strong>Compression (scenario / S1 timed):</strong> {comp_txt} &nbsp;|&nbsp; "
        f"<strong>Timed iterations:</strong> {html.escape(str(iters))} &nbsp;|&nbsp; "
        f"<code>report_version</code> {html.escape(str(ver))}</p>"
    )

    if viz_nav_html is not None:
        nav = viz_nav_html
    elif companion_stack_href or companion_summary_href:
        nav = companion_viz_nav_html(
            stack_href=companion_stack_href,
            summary_href=companion_summary_href,
            distributed_href="",
            current="distributed",
        )
    else:
        nav = ""

    fine = (
        '<p class="fineprint">Broker-backed produce/consume timings live under '
        "<code>kafka_e2e</code> in <code>report.json</code> when present; see "
        "the performance summary page for win-rate tables and full tier timings."
        "</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Distributed footprint — ksp-bench report</title>
{_DISTRIBUTED_PAGE_CSS}
</head>
<body>
{nav}
<h1>Distributed footprint</h1>
{meta}
{body}
{fine}
</body>
</html>
"""


def write_distributed_visualization(
    report_path: str | Path,
    output_path: str | Path,
    *,
    companion_stack_path: Path | None = None,
    companion_summary_path: Path | None = None,
) -> None:
    rp = Path(report_path)
    with rp.open(encoding="utf-8") as f:
        report = cast(dict[str, Any], json.load(f))
    op = Path(output_path)
    stack_p = Path(companion_stack_path) if companion_stack_path is not None else None
    sum_p = Path(companion_summary_path) if companion_summary_path is not None else None
    nav = ""
    if stack_p is not None:
        nav = build_viz_sibling_nav_html(
            current_html=op,
            stack_output=stack_p,
            summary_output=sum_p,
            distributed_output=op,
            current="distributed",
        )
    if stack_p is not None:
        stack_href = relative_viz_href(from_html=op, to_html=stack_p)
    else:
        stack_href = None
    if sum_p is not None:
        sum_href = relative_viz_href(from_html=op, to_html=sum_p)
    else:
        sum_href = None
    html_out = build_distributed_html(
        report,
        companion_stack_href=stack_href,
        companion_summary_href=sum_href,
        viz_nav_html=nav if nav else None,
    )
    op.parent.mkdir(parents=True, exist_ok=True)
    with op.open("w", encoding="utf-8") as f:
        f.write(html_out)
