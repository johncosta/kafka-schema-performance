"""Self-contained HTML stack view: encode → wire → decode, plus mean-time bars."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast

# Display order for top-level tier tabs when a report mixes row tiers.
TIER_ORDER: tuple[str, ...] = ("S0", "S1", "S2", "S3", "S4")

# Short blurbs for the HTML glossary and per-tier tab panels (keep in sync with README).
TIER_DESCRIPTIONS: dict[str, str] = {
    "S0": (
        "Codec only: timed serialize (domain→bytes) and deserialize (bytes→domain) "
        "in process. No compression inside timed encode/decode windows, no network, "
        "no schema registry."
    ),
    "S1": (
        "Codec plus timed compression on the wire: the encode window includes "
        "compressing raw bytes after serialize; decode includes decompress then "
        "deserialize. Round-trip is one timer around encode→compress→decompress→decode."
    ),
    "S2": (
        "Codec plus a loopback mock Confluent-style schema registry "
        "(GET /schemas/ids/{id} on localhost). Includes cold (new TCP each iteration) "
        "vs warm (HTTP keep-alive) registry fetch timings alongside codec timings."
    ),
    "S3": (
        "Single-record codec timings (same as S0 reference) plus an in-memory "
        "producer-style batch: encode batch_size records and bytes.join per timed "
        "iteration—no Kafka producer client or broker."
    ),
    "S4": (
        "Single-record codec timings (same as S0 reference) plus an in-memory "
        "consumer-style batch: decode batch_size prefetched payloads per timed "
        "iteration—no Kafka consumer client or broker."
    ),
}


def _tier_slug(tier: str) -> str:
    s = "".join(c if c.isalnum() else "-" for c in tier.strip().lower())
    return s or "tier"


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


def _bar_scale_maxima(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Per bar-label max mean_s across the whole report (shared width scale)."""

    out: dict[str, float] = {}
    for row in rows:
        for label, mean_s, _ in _bars_for_row(row):
            if not (mean_s == mean_s) or mean_s <= 0:
                continue
            prev = out.get(label, 0.0)
            if mean_s > prev:
                out[label] = mean_s
    return out


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


def _row_section(
    row: dict[str, Any],
    *,
    profile_in_heading: bool = True,
    bar_scale_maxima: dict[str, float] | None = None,
) -> str:
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
    row_mx = _max_bar(bars)

    bar_html: list[str] = []
    for label, mean_s, color in bars:
        if not (mean_s == mean_s) or mean_s < 0:
            continue
        if bar_scale_maxima:
            gmx = bar_scale_maxima.get(label, 0.0)
            denom = gmx if gmx > 0 else row_mx
        else:
            denom = row_mx
        pct = min(100.0, 100.0 * mean_s / denom) if denom > 0 else 0.0
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
        "from <code>report.json</code>. "
        "<strong>Width scale is shared</strong> for each bar type across <em>all</em> "
        "result rows in this file (same label = same max), so longer bars are slower "
        "than shorter ones when comparing codecs or profiles. Round-trip is one timer "
        "around encode (+ tier extras) and decode—it is <em>not</em> the sum of the "
        "encode and decode bars. See <code>measurement</code> in the report for "
        "tier-specific definitions.</p>"
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
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("payload_profile", "?")).strip() or "?"
        groups.setdefault(key, []).append(row)
    return groups


def _group_rows_by_tier(
    rows: list[dict[str, Any]],
    *,
    scenario_tier: str,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    fallback = (scenario_tier or "?").strip() or "?"
    for row in rows:
        t = str(row.get("tier") or fallback).strip() or fallback
        groups.setdefault(t, []).append(row)
    return groups


def _pick_default_tier_tab(
    scenario_tier: str,
    tier_to_rows: dict[str, list[dict[str, Any]]],
) -> str:
    """First-open tier tab: scenario tier when valid, else first tier that has rows."""

    st = (scenario_tier or "").strip()
    if st == "all":
        return TIER_ORDER[0]
    if st in TIER_ORDER:
        return st
    for t in TIER_ORDER:
        if tier_to_rows.get(t):
            return t
    return TIER_ORDER[0]


def _tier_glossary_html() -> str:
    items: list[str] = []
    for tier in TIER_ORDER:
        desc = TIER_DESCRIPTIONS.get(tier, "")
        if not desc:
            continue
        items.append(
            f"<dt><strong>{html.escape(tier)}</strong></dt>"
            f"<dd>{html.escape(desc)}</dd>",
        )
    inner = "".join(items)
    return (
        '<details class="tier-glossary">'
        "<summary>What do benchmark tiers mean?</summary>"
        f"<dl>{inner}</dl>"
        "</details>"
    )


def _scenario_tabs_html(
    profile_order: list[str],
    groups: dict[str, list[dict[str, Any]]],
    *,
    id_prefix: str,
    bar_scale_maxima: dict[str, float] | None,
) -> str:
    if not profile_order:
        return "<p>No results in report.</p>"

    tab_buttons: list[str] = []
    panels: list[str] = []
    for i, prof in enumerate(profile_order):
        slug = _profile_tab_slug(prof)
        tab_id = f"{id_prefix}tab-{slug}"
        panel_id = f"{id_prefix}panel-{slug}"
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
            _row_section(
                r,
                profile_in_heading=False,
                bar_scale_maxima=bar_scale_maxima,
            )
            for r in groups.get(prof, [])
        )
        if not inner.strip():
            inner = "<p>No rows for this profile.</p>"
        panels.append(
            f'<div class="{panel_class}" role="tabpanel" '
            f'id="{html.escape(panel_id)}" '
            f'aria-labelledby="{html.escape(tab_id)}" '
            f'tabindex="0"{hidden}>{inner}</div>',
        )

    return (
        '<div class="scenario-tabs" data-tab-group>'
        '<div class="tablist profile-tablist" role="tablist" '
        'aria-label="Payload profile (scenario)">'
        f'{"".join(tab_buttons)}'
        "</div>"
        f'{"".join(panels)}'
        "</div>"
    )


def _tier_panel_inner(
    tier: str,
    tier_rows: list[dict[str, Any]],
    scenario_profiles: list[Any],
    *,
    scenario_tier: str,
    bar_scale_maxima: dict[str, float] | None,
) -> str:
    desc = TIER_DESCRIPTIONS.get(
        tier,
        f"Tier {tier}: see the measurement block in report.json for definitions.",
    )
    desc_html = html.escape(desc)
    head = (
        f'<p class="tier-desc"><strong>{html.escape(tier)}</strong> — {desc_html}</p>'
    )
    if not tier_rows:
        st = html.escape((scenario_tier or "?").strip() or "?")
        return (
            f"{head}"
            '<p class="empty-tier">No result rows for this tier in this report. '
            f"The run was recorded at scenario tier <strong>{st}</strong> "
            "(see summary above).</p>"
        )

    groups = _group_rows_by_profile(tier_rows)
    order = _ordered_profile_keys(scenario_profiles, tier_rows)
    if not order and tier_rows:
        order = list(groups.keys())
    ts = _tier_slug(tier)
    prefix = f"prof-{ts}-"
    scenarios = _scenario_tabs_html(
        order,
        groups,
        id_prefix=prefix,
        bar_scale_maxima=bar_scale_maxima,
    )
    return f"{head}{scenarios}"


def _tier_top_tabs_html(
    all_tiers: list[str],
    tier_to_rows: dict[str, list[dict[str, Any]]],
    scenario_profiles: list[Any],
    *,
    default_tier: str,
    scenario_tier: str,
    bar_scale_maxima: dict[str, float] | None,
) -> str:
    tab_buttons: list[str] = []
    tier_panels: list[str] = []
    for tier in all_tiers:
        slug = _tier_slug(tier)
        tab_id = f"tiertab-{slug}"
        panel_id = f"tierpanel-{slug}"
        label = html.escape(tier)
        selected = tier == default_tier
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
        inner = _tier_panel_inner(
            tier,
            tier_to_rows.get(tier, []),
            scenario_profiles,
            scenario_tier=scenario_tier,
            bar_scale_maxima=bar_scale_maxima,
        )
        tier_panels.append(
            f'<div class="{panel_class}" role="tabpanel" '
            f'id="{html.escape(panel_id)}" '
            f'aria-labelledby="{html.escape(tab_id)}" '
            f'tabindex="0"{hidden}>{inner}</div>',
        )

    return (
        '<div class="tier-top" data-tab-group>'
        '<div class="tablist tier-tablist" role="tablist" aria-label="Benchmark tier">'
        f'{"".join(tab_buttons)}'
        "</div>"
        f'{"".join(tier_panels)}'
        "</div>"
    )


_TAB_SWITCH_JS = """
<script>
(function () {
  function bindTabGroup(root) {
    var tablist = root.querySelector(":scope > .tablist");
    if (!tablist) return;
    var tabs = tablist.querySelectorAll(":scope > button[data-tab-target]");
    var panels = Array.prototype.slice.call(
      root.querySelectorAll(":scope > [role=tabpanel]")
    );
    if (!tabs.length || !panels.length) return;

    function activate(panelId) {
      Array.prototype.forEach.call(tabs, function (t) {
        var on = t.getAttribute("data-tab-target") === panelId;
        t.classList.toggle("tab-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach(function (p) {
        var on = p.id === panelId;
        p.classList.toggle("tab-panel-active", on);
        if (on) {
          p.removeAttribute("hidden");
        } else {
          p.setAttribute("hidden", "");
        }
      });
    }

    root.addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-tab-target]");
      if (!btn || !tablist.contains(btn)) return;
      var id = btn.getAttribute("data-tab-target");
      if (id) activate(id);
    });

    root.addEventListener("keydown", function (e) {
      var btn = e.target.closest("button[data-tab-target]");
      if (!btn || !tablist.contains(btn)) return;
      var list = Array.prototype.slice.call(tabs);
      var idx = list.indexOf(btn);
      if (idx < 0) return;
      var next = null;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        next = list[(idx + 1) % list.length];
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        next = list[(idx - 1 + list.length) % list.length];
      } else if (e.key === "Home") {
        next = list[0];
      } else if (e.key === "End") {
        next = list[list.length - 1];
      }
      if (next) {
        e.preventDefault();
        next.focus();
        var tid = next.getAttribute("data-tab-target");
        if (tid) activate(tid);
      }
    });
  }

  document.querySelectorAll("[data-tab-group]").forEach(bindTabGroup);
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
    scenario_tier = str(scen.get("tier", "") or "")
    tier_groups = _group_rows_by_tier(rows, scenario_tier=scenario_tier)
    default_tab = _pick_default_tier_tab(scenario_tier, tier_groups)
    bar_scale_maxima = _bar_scale_maxima(rows) if rows else {}
    if rows:
        body = (
            _tier_glossary_html()
            + '<p class="summary-note">Use <strong>tier</strong> tabs (S0–S4) first, '
            "then <strong>payload profile</strong> tabs when that tier has rows. "
            "Tabs with no data explain that the run used another scenario tier. "
            "Expand <em>What do benchmark tiers mean?</em> for definitions.</p>"
            + _tier_top_tabs_html(
                list(TIER_ORDER),
                tier_groups,
                scen_profiles,
                default_tier=default_tab,
                scenario_tier=scenario_tier or "?",
                bar_scale_maxima=bar_scale_maxima,
            )
        )
    else:
        body = "<p>No results in report.</p>"

    iters_e = html.escape(str(iters))
    ver_e = html.escape(str(ver))
    summary = (
        f"<p><strong>Scenario tier:</strong> {tier} &nbsp;|&nbsp; "
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
.summary-note {
  font-size: 0.88rem;
  color: #333;
  margin: 0.75rem 0 1rem;
  line-height: 1.45;
}
.tier-glossary {
  margin: 1rem 0 0.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: #f6f8fb;
}
.tier-glossary summary {
  cursor: pointer;
  font-weight: 600;
}
.tier-glossary dl { margin: 0.75rem 0 0.25rem; }
.tier-glossary dt { margin-top: 0.5rem; }
.tier-glossary dd {
  margin: 0.15rem 0 0 1rem;
  color: #333;
  line-height: 1.45;
  max-width: 52rem;
}
.tier-top { margin-top: 0.25rem; }
.tier-tablist { margin-top: 0.5rem; }
.tier-desc {
  font-size: 0.9rem;
  line-height: 1.45;
  margin: 0 0 1rem;
  padding: 0.65rem 0.85rem;
  background: #f0f4f8;
  border-radius: 6px;
  border: 1px solid #d8e0ea;
}
.empty-tier {
  font-size: 0.88rem;
  color: #555;
  margin: 0 0 0.5rem;
  line-height: 1.45;
}
.scenario-tabs { margin-top: 0.25rem; }
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
