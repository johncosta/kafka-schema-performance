"""Self-contained HTML stack view: encode → wire → decode, plus mean-time bars."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast


def _mean_s(block: Any) -> float:
    if isinstance(block, dict):
        v = block.get("mean_s")
        if isinstance(v, (int, float)):
            x = float(v)
            return x if x == x else float("nan")
    return float("nan")


def _fmt_time(mean_s: float) -> str:
    if not (mean_s == mean_s) or mean_s < 0:
        return "n/a"
    if mean_s >= 1e-3:
        return f"{mean_s * 1e3:.3f} ms"
    return f"{mean_s * 1e6:.2f} µs"


def _bars_for_row(row: dict[str, Any]) -> list[tuple[str, float, str]]:
    """Label, mean seconds (finite), CSS color."""

    out: list[tuple[str, float, str]] = []
    enc = row.get("encode")
    dec = row.get("decode")
    rt = row.get("round_trip")
    me = _mean_s(enc)
    md = _mean_s(dec)
    mr = _mean_s(rt)
    if me == me:
        out.append(("Encode (timed window)", me, "#2d6a9f"))
    if md == md:
        out.append(("Decode (timed window)", md, "#5c4d7d"))
    if mr == mr:
        out.append(("Round-trip (single timer)", mr, "#2a8f5a"))

    s2 = row.get("s2_registry")
    if isinstance(s2, dict):
        cold = s2.get("fetch_new_tcp_each_iteration")
        warm = s2.get("fetch_reused_connection")
        mc = _mean_s(cold)
        mw = _mean_s(warm)
        if mc == mc:
            out.append(("S2: registry GET (new TCP each)", mc, "#b35a14"))
        if mw == mw:
            out.append(("S2: registry GET (keep-alive)", mw, "#c4804a"))

    s3 = row.get("s3_producer_batch")
    if isinstance(s3, dict):
        bb = s3.get("batch_build_and_join")
        mb = _mean_s(bb)
        if mb == mb:
            out.append(
                (
                    f"S3: producer batch (n={s3.get('batch_size', '?')})",
                    mb,
                    "#8b1538",
                ),
            )

    s4 = row.get("s4_consumer_batch")
    if isinstance(s4, dict):
        bd = s4.get("batch_decode")
        m4 = _mean_s(bd)
        if m4 == m4:
            out.append(
                (
                    f"S4: consumer batch decode (n={s4.get('batch_size', '?')})",
                    m4,
                    "#1f6f78",
                ),
            )

    return out


def _max_bar(bars: list[tuple[str, float, str]]) -> float:
    vals = [b[1] for b in bars if b[1] == b[1] and b[1] > 0]
    return max(vals) if vals else 1.0


def _row_section(row: dict[str, Any]) -> str:
    profile = html.escape(str(row.get("payload_profile", "?")))
    codec = html.escape(str(row.get("codec", "?")))
    tier = html.escape(str(row.get("tier", "?")))
    raw_b = row.get("raw_size_bytes")
    raw_txt = html.escape(str(raw_b)) if raw_b is not None else "?"

    bars = _bars_for_row(row)
    mx = _max_bar(bars)

    bar_html: list[str] = []
    for label, mean_s, color in bars:
        if not (mean_s == mean_s) or mean_s < 0:
            continue
        pct = min(100.0, 100.0 * mean_s / mx) if mx > 0 else 0.0
        lbl = html.escape(label)
        bar_html.append(
            f'<div class="bar-row"><div class="bar-label">{lbl}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct:.2f}%;'
            f'background:{color};"></div></div>'
            f'<div class="bar-val">{html.escape(_fmt_time(mean_s))}</div></div>',
        )

    pipeline = (
        '<div class="pipeline" aria-label="conceptual data flow">'
        '<div class="pipe-node">Domain record</div><span class="pipe-arr">→</span>'
        '<div class="pipe-node">Encode path</div><span class="pipe-arr">→</span>'
        '<div class="pipe-node">Wire bytes</div><span class="pipe-arr">→</span>'
        '<div class="pipe-node">Decode path</div><span class="pipe-arr">→</span>'
        '<div class="pipe-node">Domain record</div>'
        "</div>"
    )

    note = (
        '<p class="fineprint">Bars use <strong>mean wall time</strong> per iteration '
        "from <code>report.json</code>. Round-trip is one timer around encode "
        "(+ tier extras) and decode—it is <em>not</em> the sum of the encode and "
        "decode bars. See <code>measurement</code> in the report for tier-specific "
        "definitions.</p>"
    )

    return (
        f'<section class="result"><h2>{profile} / <code>{codec}</code> '
        f'<span class="tier">({tier})</span></h2>'
        f'<p class="meta">Mean raw wire: <strong>{raw_txt}</strong> bytes</p>'
        f"{pipeline}{note}"
        f'<div class="bars">{"".join(bar_html)}</div></section>'
    )


def build_stack_html(report: dict[str, Any]) -> str:
    scen = report.get("scenario")
    if not isinstance(scen, dict):
        scen = {}
    tier = html.escape(str(scen.get("tier", "?")))
    profiles = scen.get("payload_profiles", [])
    prof_txt = html.escape(", ".join(str(p) for p in profiles) if profiles else "?")
    iters = scen.get("timed_iterations", "?")
    ver = report.get("report_version", "?")

    sections: list[str] = []
    for row in report.get("results", []):
        if isinstance(row, dict):
            sections.append(_row_section(row))

    body = "\n".join(sections) if sections else "<p>No results in report.</p>"

    iters_e = html.escape(str(iters))
    ver_e = html.escape(str(ver))
    summary = (
        f"<p><strong>Tier:</strong> {tier} &nbsp;|&nbsp; "
        f"<strong>Profiles:</strong> {prof_txt} &nbsp;|&nbsp; "
        f"<strong>Timed iterations:</strong> {iters_e} &nbsp;|&nbsp; "
        f"<code>report_version</code> {ver_e}</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Stack visualization — ksp-bench report</title>
{_STACK_PAGE_CSS}
</head>
<body>
<h1>Serialization stack &amp; component times</h1>
{summary}
{body}
</body>
</html>
"""


_STACK_PAGE_CSS = """
<style>
body {
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  margin: 1.5rem;
  max-width: 56rem;
  color: #1a1a1a;
}
h1 { font-size: 1.35rem; }
.result {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
  background: #fafafa;
}
.result h2 { margin-top: 0; font-size: 1.1rem; }
.tier { color: #555; font-weight: normal; }
.meta { margin: 0.25rem 0 0.75rem; font-size: 0.9rem; }
.pipeline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin: 0.75rem 0;
  font-size: 0.85rem;
}
.pipe-node {
  background: #e8eef5;
  border: 1px solid #c5d4e8;
  border-radius: 6px;
  padding: 0.35rem 0.55rem;
}
.pipe-arr { color: #666; }
.bars { margin-top: 1rem; }
.bar-row {
  display: grid;
  grid-template-columns: minmax(12rem, 1fr) 4fr auto;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 0.5rem;
}
.bar-label { font-size: 0.88rem; }
.bar-track {
  background: #e9e9e9;
  border-radius: 4px;
  height: 1.35rem;
  overflow: hidden;
}
.bar-fill { height: 100%; border-radius: 4px; min-width: 2px; }
.bar-val {
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.fineprint {
  font-size: 0.8rem;
  color: #444;
  margin: 0.5rem 0 0.75rem;
  line-height: 1.4;
}
</style>
""".strip()


def write_stack_visualization(report_path: str | Path, output_path: str | Path) -> None:
    rp = Path(report_path)
    with rp.open(encoding="utf-8") as f:
        report = cast(dict[str, Any], json.load(f))
    html_out = build_stack_html(report)
    op = Path(output_path)
    op.parent.mkdir(parents=True, exist_ok=True)
    with op.open("w", encoding="utf-8") as f:
        f.write(html_out)
