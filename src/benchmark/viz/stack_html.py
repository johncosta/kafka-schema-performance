"""Self-contained HTML stack view: encode → wire → decode, plus mean-time bars."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast


def _profile_tab_slug(profile: str) -> str:
    """ASCII id for tab/panel ids (payload_profile values are enum-like)."""

    s = "".join(c if c.isalnum() else "-" for c in profile.strip().lower())
    return s or "profile"


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


def _phase3_probe_sizes(row: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return (gzip_bytes, zstd_bytes) from Phase-3 wire-size probes, if present."""

    cpp = row.get("compressed_payload_bytes")
    if not isinstance(cpp, dict):
        return None, None
    gz = cpp.get("gzip")
    zs = cpp.get("zstd")
    gb = gz.get("bytes") if isinstance(gz, dict) else None
    zb = zs.get("bytes") if isinstance(zs, dict) else None
    gi = int(gb) if isinstance(gb, int) else None
    zi = int(zb) if isinstance(zb, int) else None
    return gi, zi


def _row_section(row: dict[str, Any], *, profile_in_heading: bool = True) -> str:
    profile = html.escape(str(row.get("payload_profile", "?")))
    codec = html.escape(str(row.get("codec", "?")))
    tier = html.escape(str(row.get("tier", "?")))
    raw_b = row.get("raw_size_bytes")
    raw_txt = html.escape(str(raw_b)) if raw_b is not None else "?"

    meta_lines: list[str] = [
        f'<p class="meta">Mean raw wire: <strong>{raw_txt}</strong> bytes</p>',
    ]
    gz_b, zs_b = _phase3_probe_sizes(row)
    if gz_b is not None and zs_b is not None:
        meta_lines.append(
            '<p class="meta fine">Phase-3 size probes on raw wire: '
            f"<strong>gzip</strong> {html.escape(str(gz_b))} bytes &nbsp;|&nbsp; "
            f"<strong>zstd</strong> {html.escape(str(zs_b))} bytes "
            "(levels from <code>scenario.size_and_cost</code>; not the S1 timed "
            "compressor unless tier is S1).</p>",
        )
    if row.get("tier") == "S1":
        comp_b = row.get("compressed_size_bytes")
        row_comp = row.get("compression")
        if comp_b is not None:
            alg = html.escape(str(row_comp)) if row_comp is not None else "?"
            meta_lines.append(
                f'<p class="meta fine">S1 timed wire (after <strong>{alg}</strong>): '
                f"<strong>{html.escape(str(comp_b))}</strong> bytes</p>",
            )

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

    title = (
        f'{profile} / <code>{codec}</code> <span class="tier">({tier})</span>'
        if profile_in_heading
        else f'<code>{codec}</code> <span class="tier">({tier})</span>'
    )

    return (
        f'<section class="result"><h2>{title}</h2>'
        f'{"".join(meta_lines)}'
        f"{pipeline}{note}"
        f'<div class="bars">{"".join(bar_html)}</div></section>'
    )


def _ordered_profile_keys(
    scenario_profiles: list[Any],
    rows: list[dict[str, Any]],
) -> list[str]:
    """Tab order: scenario payload_profiles first, then any extra profiles from rows."""

    seen: set[str] = set()
    out: list[str] = []
    for p in scenario_profiles:
        key = str(p).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    for row in rows:
        key = str(row.get("payload_profile", "")).strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _group_rows_by_profile(
    rows: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("payload_profile", "?")).strip() or "?"
        groups.setdefault(key, []).append(row)
    return groups


def _scenario_tabs_html(
    profile_order: list[str], groups: dict[str, list[dict[str, Any]]]
) -> str:
    if not profile_order:
        return "<p>No results in report.</p>"

    tab_buttons: list[str] = []
    panels: list[str] = []
    for i, prof in enumerate(profile_order):
        slug = _profile_tab_slug(prof)
        tab_id = f"tab-{slug}"
        panel_id = f"tabpanel-{slug}"
        label = html.escape(prof)
        selected = i == 0
        aria_sel = "true" if selected else "false"
        tab_class = "tab" + (" tab-active" if selected else "")
        panel_class = "tab-panel" + (" tab-panel-active" if selected else "")
        hidden = "" if selected else ' hidden=""'
        tab_buttons.append(
            f'<button type="button" class="{tab_class}" role="tab" '
            f'id="{html.escape(tab_id)}" aria-selected="{aria_sel}" '
            f'aria-controls="{html.escape(panel_id)}" '
            f'data-tab-target="{html.escape(panel_id)}">{label}</button>',
        )
        inner = "\n".join(
            _row_section(r, profile_in_heading=False) for r in groups.get(prof, [])
        )
        if not inner.strip():
            inner = "<p>No rows for this profile.</p>"
        panels.append(
            f'<div class="{panel_class}" role="tabpanel" '
            f'id="{html.escape(panel_id)}" '
            f'aria-labelledby="{html.escape(tab_id)}" '
            f'tabindex="0"{hidden}>{inner}</div>',
        )

    tabs_row = (
        '<div class="scenario-tabs" data-scenario-tabs>'
        '<div class="tablist" role="tablist" aria-label="Payload profile (scenario)">'
        f'{"".join(tab_buttons)}'
        "</div>"
        f'{"".join(panels)}'
        "</div>"
    )
    return tabs_row


_TAB_SWITCH_JS = """
<script>
(function () {
  var root = document.querySelector("[data-scenario-tabs]");
  if (!root) return;
  var tabs = root.querySelectorAll("button[data-tab-target]");
  var panels = root.querySelectorAll("[role=tabpanel]");
  function activate(panelId) {
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-tab-target") === panelId;
      t.classList.toggle("tab-active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    panels.forEach(function (p) {
      var on = p.id === panelId;
      p.classList.toggle("tab-panel-active", on);
      if (on) { p.removeAttribute("hidden"); } else { p.setAttribute("hidden", ""); }
    });
  }
  root.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-tab-target]");
    if (!btn || !root.contains(btn)) return;
    var id = btn.getAttribute("data-tab-target");
    if (id) activate(id);
  });
  root.addEventListener("keydown", function (e) {
    var btn = e.target.closest("button[data-tab-target]");
    if (!btn || !root.contains(btn)) return;
    var list = Array.prototype.slice.call(tabs);
    var idx = list.indexOf(btn);
    if (idx < 0) return;
    var next = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      next = list[(idx + 1) % list.length];
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      next = list[(idx - 1 + list.length) % list.length];
    } else if (e.key === "Home") { next = list[0]; }
    else if (e.key === "End") { next = list[list.length - 1]; }
    if (next) {
      e.preventDefault();
      next.focus();
      var tid = next.getAttribute("data-tab-target");
      if (tid) activate(tid);
    }
  });
})();
</script>
"""


def build_stack_html(report: dict[str, Any]) -> str:
    scen = report.get("scenario")
    if not isinstance(scen, dict):
        scen = {}
    tier = html.escape(str(scen.get("tier", "?")))
    profiles = scen.get("payload_profiles", [])
    prof_txt = html.escape(", ".join(str(p) for p in profiles) if profiles else "?")
    fmt_list = scen.get("formats", [])
    fmt_txt = html.escape(", ".join(str(x) for x in fmt_list) if fmt_list else "?")
    comp = scen.get("compression")
    comp_txt = html.escape(str(comp)) if comp is not None else "?"
    iters = scen.get("timed_iterations", "?")
    ver = report.get("report_version", "?")

    raw_results = report.get("results", [])
    rows: list[dict[str, Any]] = [r for r in raw_results if isinstance(r, dict)]
    scen_profiles_raw = profiles if isinstance(profiles, list) else []
    scen_profiles = [p for p in scen_profiles_raw if p is not None]
    groups = _group_rows_by_profile(rows)
    order = _ordered_profile_keys(scen_profiles, rows)
    if not order and rows:
        order = list(groups.keys())
    body = (
        _scenario_tabs_html(order, groups) if rows else "<p>No results in report.</p>"
    )

    iters_e = html.escape(str(iters))
    ver_e = html.escape(str(ver))
    summary = (
        f"<p><strong>Tier:</strong> {tier} &nbsp;|&nbsp; "
        f"<strong>Profiles:</strong> {prof_txt} &nbsp;|&nbsp; "
        f"<strong>Formats:</strong> {fmt_txt} &nbsp;|&nbsp; "
        f"<strong>Compression (scenario / S1 timed):</strong> {comp_txt} &nbsp;|&nbsp; "
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
{_TAB_SWITCH_JS}
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
.meta.fine { font-size: 0.82rem; color: #444; margin-top: -0.35rem; }
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
.scenario-tabs { margin-top: 1rem; }
.tablist {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid #ccc;
  padding-bottom: 0.35rem;
}
.tab {
  font: inherit;
  cursor: pointer;
  padding: 0.45rem 0.85rem;
  border: 1px solid transparent;
  border-radius: 6px 6px 0 0;
  background: #eee;
  color: #333;
}
.tab:hover { background: #e2e2e2; }
.tab:focus-visible { outline: 2px solid #2d6a9f; outline-offset: 2px; }
.tab.tab-active {
  background: #fafafa;
  border-color: #ccc;
  border-bottom-color: #fafafa;
  margin-bottom: -1px;
  font-weight: 600;
}
.tab-panel { margin-top: 0; }
.tab-panel[hidden] { display: none !important; }
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
