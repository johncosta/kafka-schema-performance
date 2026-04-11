"""Self-contained HTML page: scenario-aware conclusions from benchmark results."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, cast

from benchmark.viz.stack_html import (
    TIER_ORDER,
    _fmt_time,
    _mean_s,
    build_viz_sibling_nav_html,
    companion_viz_nav_html,
    relative_viz_href,
)

# Ratio above which we call a timing gap "large" in prose (micro-benchmark noise).
_SPREAD_NOTE_RATIO = 1.15


def _mean_wire_bytes(row: dict[str, Any]) -> float | None:
    re = row.get("raw_encoded_bytes")
    if isinstance(re, dict):
        m = re.get("mean")
        if isinstance(m, (int, float)):
            x = float(m)
            return x if x == x else None
    rs = row.get("raw_size_bytes")
    if isinstance(rs, (int, float)):
        x = float(rs)
        return x if x == x else None
    return None


def _s1_timed_compressed_bytes(row: dict[str, Any]) -> int | None:
    if row.get("tier") != "S1":
        return None
    cs = row.get("compressed_size_bytes")
    if isinstance(cs, int):
        return cs
    if isinstance(cs, float) and cs == cs:
        return int(round(cs))
    s1 = row.get("s1_timed_compression")
    if isinstance(s1, dict):
        cb = s1.get("compressed_bytes")
        if isinstance(cb, int):
            return cb
        if isinstance(cb, float) and cb == cb:
            return int(round(cb))
    return None


def _s3_batch_mean(row: dict[str, Any]) -> float | None:
    s3 = row.get("s3_producer_batch")
    if not isinstance(s3, dict):
        return None
    return _mean_s(s3.get("batch_build_and_join"))


def _s4_batch_mean(row: dict[str, Any]) -> float | None:
    s4 = row.get("s4_consumer_batch")
    if not isinstance(s4, dict):
        return None
    return _mean_s(s4.get("batch_decode"))


def _codec(row: dict[str, Any]) -> str:
    return str(row.get("codec", "?")).strip() or "?"


def _tier(row: dict[str, Any]) -> str:
    return str(row.get("tier", "?")).strip() or "?"


def _profile(row: dict[str, Any]) -> str:
    return str(row.get("payload_profile", "?")).strip() or "?"


def _group_rows(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (_tier(row), _profile(row))
        out.setdefault(key, []).append(row)
    for group in out.values():
        group.sort(key=_codec)
    return out


def _profile_order(
    scenario_profiles: list[Any],
    tier_rows: list[dict[str, Any]],
) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for p in scenario_profiles:
        ps = str(p).strip()
        if ps and ps not in seen:
            order.append(ps)
            seen.add(ps)
    for row in tier_rows:
        ps = _profile(row)
        if ps not in seen:
            order.append(ps)
            seen.add(ps)
    return order


def _tier_sort_key(tier: str) -> tuple[int, str]:
    if tier in TIER_ORDER:
        return (TIER_ORDER.index(tier), tier)
    return (len(TIER_ORDER), tier)


def _group_win_races(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, float]]]:
    """Metrics where at least two codecs have comparable scores (lower is better)."""

    if len(rows) < 2:
        return []
    tier = _tier(rows[0])
    races: list[tuple[str, dict[str, float]]] = []
    for label, key in (
        ("Encode", "encode"),
        ("Decode", "decode"),
        ("Round-trip", "round_trip"),
    ):
        scored = {c: m for c, m in _rank_by_mean(rows, key)}
        if len(scored) >= 2:
            races.append((label, scored))
    wire: dict[str, float] = {}
    for r in rows:
        w = _mean_wire_bytes(r)
        if w is not None and w == w and w > 0:
            wire[_codec(r)] = w
    if len(wire) >= 2:
        races.append(("Raw wire (mean bytes)", wire))
    if tier == "S1":
        s1: dict[str, float] = {}
        for r in rows:
            b = _s1_timed_compressed_bytes(r)
            if b is not None and b > 0:
                s1[_codec(r)] = float(b)
        if len(s1) >= 2:
            races.append(("S1 timed compressed (bytes)", s1))
    if tier == "S3":
        s3: dict[str, float] = {}
        for r in rows:
            m3 = _s3_batch_mean(r)
            if m3 is not None and m3 == m3 and m3 > 0:
                s3[_codec(r)] = m3
        if len(s3) >= 2:
            races.append(("S3 producer batch (mean s)", s3))
    if tier == "S4":
        s4: dict[str, float] = {}
        for r in rows:
            m4 = _s4_batch_mean(r)
            if m4 is not None and m4 == m4 and m4 > 0:
                s4[_codec(r)] = m4
        if len(s4) >= 2:
            races.append(("S4 consumer batch decode (mean s)", s4))
    return races


def _min_value_winners(scores: dict[str, float]) -> list[str]:
    if not scores:
        return []
    best = min(scores.values())
    return [c for c, v in scores.items() if v == best]


def group_rows_for_win_rate(
    rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Partition ``results`` rows by ``(tier, payload_profile)`` for win-rate math."""

    return _group_rows(rows)


def aggregate_codec_win_rates(
    groups: dict[tuple[str, str], list[dict[str, Any]]],
    all_rows: list[dict[str, Any]],
) -> tuple[int, dict[str, float], list[str]]:
    """Public entrypoint for win-rate aggregation (PRD §6.6.7 tests, viz parity)."""

    return _aggregate_codec_win_rates(groups, all_rows)


def _aggregate_codec_win_rates(
    groups: dict[tuple[str, str], list[dict[str, Any]]],
    all_rows: list[dict[str, Any]],
) -> tuple[int, dict[str, float], list[str]]:
    """Count comparisons; win_points per codec (ties split 1/k); sorted codec names."""

    win_points: dict[str, float] = {}
    n_comparisons = 0
    for grp in groups.values():
        if len(grp) < 2:
            continue
        for _label, scores in _group_win_races(grp):
            winners = _min_value_winners(scores)
            if not winners:
                continue
            n_comparisons += 1
            share = 1.0 / len(winners)
            for c in winners:
                win_points[c] = win_points.get(c, 0.0) + share
    all_codecs = sorted({_codec(r) for r in all_rows})
    for c in all_codecs:
        win_points.setdefault(c, 0.0)
    sorted_by_pts = sorted(
        all_codecs,
        key=lambda c: (-win_points.get(c, 0.0), c),
    )
    return n_comparisons, win_points, sorted_by_pts


def _win_rate_section(
    groups: dict[tuple[str, str], list[dict[str, Any]]],
    all_rows: list[dict[str, Any]],
) -> str:
    n, win_pts, order = _aggregate_codec_win_rates(groups, all_rows)
    if n <= 0:
        return (
            '<section class="win-rate"><h2>Win rate across comparisons</h2>'
            "<p>No head-to-head comparisons: need at least two codecs in the same "
            "<strong>tier × profile</strong> with overlapping metrics.</p></section>"
        )
    intro = (
        f"<p>Across <strong>{html.escape(str(n))}</strong> comparisons, each "
        "picks the <strong>fastest</strong> mean time or <strong>smallest</strong> "
        "size among codecs in that tier and payload profile. Metrics counted: "
        "encode, decode, round-trip, raw wire (when ≥2 codecs have sizes), and "
        "S1/S3/S4 extras when present. <strong>Ties</strong> split one point "
        "equally (two winners → 0.5 each).</p>"
    )
    thead = "<tr><th>Codec</th><th>Win share</th>" "<th>% of comparisons</th></tr>"
    body: list[str] = []
    for c in order:
        pts = win_pts.get(c, 0.0)
        pct = 100.0 * pts / n if n else 0.0
        body.append(
            "<tr>"
            f"<td><code>{html.escape(c)}</code></td>"
            f'<td class="num">{html.escape(f"{pts:.2f}")}</td>'
            f'<td class="num"><strong>{html.escape(f"{pct:.1f}")}%</strong></td>'
            "</tr>",
        )
    tbl = (
        '<table class="matrix win-rate-table"><thead>'
        f"{thead}</thead><tbody>{''.join(body)}</tbody></table>"
    )
    fine = (
        '<p class="fineprint">Win share sums to the number of comparisons when '
        "there are no ties; with ties, total share still equals that count. "
        "Codecs with <strong>0%</strong> never ranked alone fastest on a counted "
        "metric.</p>"
    )
    return (
        '<section class="win-rate"><h2>Win rate across comparisons</h2>'
        f"{intro}{tbl}{fine}</section>"
    )


def _rank_by_mean(
    rows: list[dict[str, Any]],
    block_key: str,
) -> list[tuple[str, float]]:
    scored: list[tuple[str, float]] = []
    for row in rows:
        m = _mean_s(row.get(block_key))
        if m == m and m > 0:
            scored.append((_codec(row), m))
    scored.sort(key=lambda x: x[1])
    return scored


def _spread_ratio(ranked: list[tuple[str, float]]) -> float | None:
    if len(ranked) < 2:
        return None
    lo = ranked[0][1]
    hi = ranked[-1][1]
    if lo <= 0:
        return None
    return hi / lo


def _winner_loser_sentence(
    metric_label: str,
    ranked: list[tuple[str, float]],
) -> str | None:
    if len(ranked) < 2:
        return None
    fastest, t_fast = ranked[0]
    slowest, t_slow = ranked[-1]
    ratio = _spread_ratio(ranked)
    if ratio is None or ratio < _SPREAD_NOTE_RATIO:
        return None
    rf = html.escape(fastest)
    rs = html.escape(slowest)
    ml = html.escape(metric_label)
    return (
        f"For <strong>{ml}</strong>, <code>{rf}</code> was fastest "
        f"({html.escape(_fmt_time(t_fast))}); <code>{rs}</code> slowest "
        f"({html.escape(_fmt_time(t_slow))}, ~{ratio:.2f}×)."
    )


def _collect_headline_bullets(
    groups: dict[tuple[str, str], list[dict[str, Any]]],
    max_bullets: int = 10,
) -> list[str]:
    bullets: list[str] = []
    keys_sorted = sorted(groups.keys(), key=lambda k: (_tier_sort_key(k[0]), k[1]))
    for tier, profile in keys_sorted:
        if len(bullets) >= max_bullets:
            break
        rows = groups[(tier, profile)]
        if len(rows) < 2:
            continue
        rt_rank = _rank_by_mean(rows, "round_trip")
        sent = _winner_loser_sentence(
            f"{tier} round-trip ({profile})",
            rt_rank,
        )
        if sent:
            bullets.append(f"<li>{sent}</li>")
    if not bullets:
        bullets.append(
            "<li>Cross-codec timing gaps are modest in this report under the "
            f"{_SPREAD_NOTE_RATIO:.2f}× headline threshold, or fewer than two codecs "
            "per cell—see per-tier tables for exact means.</li>",
        )
    return bullets


def _regression_block(report: dict[str, Any]) -> str:
    rc = report.get("regression_check")
    if not isinstance(rc, dict) or rc.get("skipped"):
        return ""
    warns = rc.get("warnings")
    if not isinstance(warns, list) or not warns:
        return ""
    items = []
    for w in warns:
        if isinstance(w, dict):
            msg = w.get("message", str(w))
        else:
            msg = str(w)
        items.append(f"<li>{html.escape(msg)}</li>")
    return (
        '<section class="callout warn"><h2>Regression hints</h2>'
        "<p>Baseline comparison reported warnings:</p>"
        f"<ul>{''.join(items)}</ul></section>"
    )


def _kafka_e2e_mb_s_cell(block: dict[str, Any], key: str) -> str:
    v = block.get(key)
    if isinstance(v, (int, float)) and v == v:
        return html.escape(f"{float(v):.2f}")
    return "—"


def _kafka_e2e_section(report: dict[str, Any]) -> str:
    block = report.get("kafka_e2e")
    if not isinstance(block, dict):
        return ""
    ver = block.get("kafka_e2e_version", "?")
    impl = html.escape(str(block.get("broker_implementation", "?")))
    boot = html.escape(str(block.get("bootstrap_servers", "?")))
    client_html = ""
    cli = block.get("client")
    if isinstance(cli, dict):
        lib = html.escape(str(cli.get("library", "?")))
        av = html.escape(json.dumps(cli.get("api_version"), separators=(",", ":")))
        client_html = (
            f"<p><strong>Client:</strong> <code>{lib}</code> "
            f'<span class="meta">api_version={av}</span></p>'
        )
    cfg_html = ""
    pc = block.get("producer_config")
    cc = block.get("consumer_config")
    if isinstance(pc, dict) or isinstance(cc, dict):
        parts: list[str] = [
            "<details><summary>Producer / consumer config (snapshot)</summary>"
        ]
        if isinstance(pc, dict):
            parts.append(
                '<p><strong>Producer</strong></p><pre class="cfg-pre">'
                f"{html.escape(json.dumps(pc, indent=2, sort_keys=True, default=str))}"
                "</pre>",
            )
        if isinstance(cc, dict):
            parts.append(
                '<p><strong>Consumer</strong></p><pre class="cfg-pre">'
                f"{html.escape(json.dumps(cc, indent=2, sort_keys=True, default=str))}"
                "</pre>",
            )
        parts.append("</details>")
        cfg_html = "".join(parts)
    roadmap = block.get("roadmap")
    roadmap_html = ""
    if isinstance(roadmap, str) and roadmap.strip():
        roadmap_html = (
            f'<p class="fineprint"><strong>Roadmap (PRD §6.3.1):</strong> '
            f"{html.escape(roadmap.strip())}</p>"
        )
    phases = block.get("phases")
    phase_ul = ""
    if isinstance(phases, dict) and phases:
        lis = []
        for k, v in phases.items():
            if isinstance(v, str):
                k_esc = html.escape(str(k))
                v_esc = html.escape(v)
                lis.append(f"<li><strong>{k_esc}:</strong> {v_esc}</li>")
        if lis:
            phase_ul = f"<ul>{''.join(lis)}</ul>"
    cases = block.get("cases")
    rows: list[str] = []
    if isinstance(cases, list):
        for c in cases:
            if not isinstance(c, dict):
                continue
            codec = html.escape(str(c.get("codec", "?")))
            prof = html.escape(str(c.get("payload_profile", "?")))
            vb = c.get("value_bytes", "?")
            ser = c.get("serialize")
            pr = c.get("produce")
            co = c.get("consume")
            ser_m = ""
            if isinstance(ser, dict):
                ms = ser.get("mean_s")
                if isinstance(ms, (int, float)) and ms == ms:
                    ser_m = html.escape(f"{float(ms) * 1e6:.2f} µs")
            pr_m = ""
            pr_mb = "—"
            if isinstance(pr, dict):
                mp = pr.get("mean_per_message_s")
                if isinstance(mp, (int, float)) and mp == mp:
                    pr_m = html.escape(f"{float(mp) * 1e3:.3f} ms/msg")
                pr_mb = _kafka_e2e_mb_s_cell(pr, "throughput_megabytes_per_s")
            co_m = ""
            co_mb = "—"
            if isinstance(co, dict):
                mc = co.get("mean_per_message_s")
                if isinstance(mc, (int, float)) and mc == mc:
                    co_m = html.escape(f"{float(mc) * 1e3:.3f} ms/msg")
                co_mb = _kafka_e2e_mb_s_cell(co, "throughput_megabytes_per_s")
            rows.append(
                "<tr>"
                f"<td><code>{codec}</code></td>"
                f"<td>{prof}</td>"
                f"<td>{html.escape(str(vb))}</td>"
                f"<td>{ser_m or '—'}</td>"
                f"<td>{pr_m or '—'}</td>"
                f'<td class="num">{pr_mb}</td>'
                f"<td>{co_m or '—'}</td>"
                f'<td class="num">{co_mb}</td>'
                "</tr>",
            )
    thead = (
        "<tr><th>Codec</th><th>Profile</th><th>Value bytes</th>"
        "<th>Serialize (mean)</th><th>Produce (mean/msg)</th>"
        '<th class="num">Produce MB/s</th>'
        "<th>Consume (mean/msg)</th>"
        '<th class="num">Consume MB/s</th></tr>'
    )
    tbl = (
        '<table class="matrix"><thead>'
        f"{thead}</thead><tbody>{''.join(rows)}</tbody></table>"
    )
    fine = (
        '<p class="fineprint">Broker-backed metrics are <strong>not</strong> '
        "tier S0–S4; they measure real Kafka-protocol I/O plus in-process "
        "serialize. Throughput columns use value bytes × message counts over "
        "the timed wall interval (consume includes warmup+timed messages). "
        f"<code>kafka_e2e_version</code> {html.escape(str(ver))}.</p>"
    )
    return (
        '<section class="kafka-e2e"><h2>Kafka-protocol end-to-end</h2>'
        f"<p><strong>Broker:</strong> {impl} &nbsp;|&nbsp; "
        f"<strong>Bootstrap:</strong> <code>{boot}</code></p>"
        f"{client_html}{cfg_html}{roadmap_html}{phase_ul}{tbl}{fine}</section>"
    )


def _limitations_block(report: dict[str, Any]) -> str:
    lim = report.get("limitations")
    if not isinstance(lim, dict):
        return ""
    parts: list[str] = []
    summ = lim.get("summary")
    if isinstance(summ, str) and summ.strip():
        parts.append(f"<p>{html.escape(summ.strip())}</p>")
    pol = lim.get("interpretation_policy")
    if isinstance(pol, str) and pol.strip():
        parts.append(f"<p><strong>Policy:</strong> {html.escape(pol.strip())}</p>")
    pts = lim.get("points")
    if isinstance(pts, list) and pts:
        lis = []
        for p in pts[:12]:
            if isinstance(p, str) and p.strip():
                lis.append(f"<li>{html.escape(p.strip())}</li>")
        if lis:
            parts.append(f"<ul>{''.join(lis)}</ul>")
    cov = lim.get("evidence_coverage")
    if isinstance(cov, dict):
        nm = cov.get("not_measured")
        if isinstance(nm, list) and nm:
            ev_lis = []
            for x in nm[:8]:
                if isinstance(x, str) and x.strip():
                    ev_lis.append(f"<li>{html.escape(x.strip())}</li>")
            if ev_lis:
                parts.append(
                    "<p><strong>PRD §6.6 — not measured here:</strong></p>"
                    f"<ul>{''.join(ev_lis)}</ul>"
                )
    if not parts:
        return ""
    return (
        '<section class="caveats"><h2>Limitations &amp; caveats</h2>'
        f'{"".join(parts)}</section>'
    )


_TEST_SUITE_AI_HANDOFF_LINES: tuple[str, ...] = (
    "# kafka-schema-performance — pytest inventory (handoff for gap analysis)",
    "",
    "## How to use this block",
    "Copy everything below the next line into another model together with "
    "report.json and/or this summary. Ask for missing tests, contradictory "
    "assumptions, and coverage vs. the PRD.",
    "---",
    "",
    "## How to run",
    "- `pytest` — full tree under tests/; fast by default.",
    '- `make test-ci` — CI default: pytest -m "not kafka" + ksp-bench S0–S4 smokes '
    "(no Docker).",
    "- `@pytest.mark.kafka` — skipped unless KSP_KAFKA_BOOTSTRAP=host:port "
    "(e.g. Docker Compose Kafka KRaft) or KSP_USE_TESTCONTAINERS=1 with .[kafka].",
    "- `pytest -m distributed` — only tests marked @pytest.mark.distributed.",
    "- `pytest -m kafka` — only broker integration tests.",
    "- `make test` — compose Kafka, full pytest + kafka, then ksp-bench smokes.",
    "",
    "## Pytest markers (pyproject.toml)",
    "- distributed — in-process S0/S1 footprint vs. binary codecs "
    "(tests/test_distributed_performance.py).",
    "- kafka — real broker produce/consume + kafka_e2e report merge "
    "(tests/integration/test_kafka_distributed.py).",
    "",
    "## tests/ — in-process (no broker required)",
    "- test_cli_parse.py — CLI argument parsing / typer wiring.",
    "- test_codecs.py — Avro / Protobuf / JSON encode-decode round-trips.",
    "- test_codecs_negative_decode.py — invalid wire / JSON; expected failures.",
    "- test_distributed_performance.py — @pytest.mark.distributed: large/medium "
    "S0 wire JSON > binary; large S1 compressed JSON > binary.",
    "- test_env_integrity.py — fixture / environment checksum behavior.",
    "- test_generators.py — synthetic payload generator invariants.",
    "- test_golden_report_win_rate.py — examples/reports golden JSON; win-rate math.",
    "- test_registry_mock.py — tier S2 mock schema registry HTTP path.",
    "- test_report_render.py — Markdown report rendering from JSON.",
    "- test_regression.py — baseline fingerprint and regression_warn_ratio hints.",
    "- test_rubrics.py — governance / maintainability YAML merge into report.",
    "- test_runner.py — bench_codec matrix, tiers S0–S4 shape, kafka_shaped sizes, "
    "S1 s1_phase_isolation.",
    "- test_stats.py — timing stats helpers.",
    "- test_metrics_stats_canned.py — fixed-sample percentiles; gzip/zstd helpers.",
    "- test_viz_distributed_html.py — distributed.html from report rows.",
    "- test_viz_stack_html.py — stack tier tabs, bars, glossary HTML.",
    "- test_viz_summary_html.py — summary tables, win-rate, kafka_e2e HTML block.",
    "",
    "## tests/integration/",
    "- conftest.py — session kafka_bootstrap_servers from env or Testcontainers.",
    "- test_kafka_distributed.py — @pytest.mark.kafka: benchmark_kafka_case, "
    "report kafka_e2e attachment.",
    "",
    "## Artifacts vs. tests",
    "- This summary HTML is generated by `ksp-bench viz`; it is not itself "
    "asserted except via test_viz_summary_html.py.",
    "- report.json schema evolves (report_version); tests pin behaviors not every "
    "optional field.",
    "",
    "## Suggested review prompts (paste into the other model)",
    "1. Given this report's scenario (tier, profiles, formats), which tiers or "
    "metrics have no automated assertion?",
    "2. Where could JSON outperform binary codecs without the suite failing?",
    "3. List integration gaps: auth, TLS, multi-broker, schema registry with "
    "real Confluent stack, consumer lag, poison messages.",
    "4. Do visualization pages claim anything not backed by tests?",
    "5. What would you add for CI on a runner without Docker?",
)


def _test_suite_ai_handoff_section() -> str:
    """Plain-text inventory for copy-paste into another system for gap analysis."""

    text = "\n".join(_TEST_SUITE_AI_HANDOFF_LINES)
    esc = html.escape(text)
    return (
        '<section class="ai-handoff">'
        "<h2>Test suite (for external review)</h2>"
        "<p>Structured inventory of the pytest tree and how to run it. Expand "
        "the block, select all text inside the grey box, and copy into another "
        "model with <code>report.json</code> for coverage and gap analysis.</p>"
        "<details><summary>Open plain-text handoff</summary>"
        f'<pre class="ai-handoff-pre" tabindex="0">{esc}</pre>'
        "</details></section>"
    )


def _comparison_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No rows.</p>"

    enc_r = {c: m for c, m in _rank_by_mean(rows, "encode")}
    dec_r = {c: m for c, m in _rank_by_mean(rows, "decode")}
    rt_r = {c: m for c, m in _rank_by_mean(rows, "round_trip")}
    codecs = [_codec(r) for r in rows]

    def col_min(d: dict[str, float]) -> float | None:
        vals = [x for x in d.values() if x == x and x > 0]
        return min(vals) if vals else None

    enc_best = col_min(enc_r)
    dec_best = col_min(dec_r)
    rt_best = col_min(rt_r)

    wire_vals: dict[str, float] = {}
    for r in rows:
        w = _mean_wire_bytes(r)
        if w is not None and w == w and w > 0:
            wire_vals[_codec(r)] = w
    wire_best = min(wire_vals.values()) if wire_vals else None

    s1_vals: dict[str, int] = {}
    for r in rows:
        b = _s1_timed_compressed_bytes(r)
        if b is not None and b > 0:
            s1_vals[_codec(r)] = b
    s1_best = min(s1_vals.values()) if s1_vals else None

    s3_vals: dict[str, float] = {}
    for r in rows:
        m3 = _s3_batch_mean(r)
        if m3 is not None and m3 == m3 and m3 > 0:
            s3_vals[_codec(r)] = m3
    s3_best = min(s3_vals.values()) if s3_vals else None

    s4_vals: dict[str, float] = {}
    for r in rows:
        m4 = _s4_batch_mean(r)
        if m4 is not None and m4 == m4 and m4 > 0:
            s4_vals[_codec(r)] = m4
    s4_best = min(s4_vals.values()) if s4_vals else None

    headers = ["Codec", "Encode", "Decode", "Round-trip"]
    has_wire = bool(wire_vals)
    has_s1 = bool(s1_vals)
    has_s3 = bool(s3_vals)
    has_s4 = bool(s4_vals)
    if has_wire:
        headers.append("Raw wire (mean B)")
    if has_s1:
        headers.append("S1 timed compressed (B)")
    if has_s3:
        headers.append("S3 batch (mean s)")
    if has_s4:
        headers.append("S4 batch decode (mean s)")

    thead = "<tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr>"

    body_rows: list[str] = []
    for c in sorted(codecs):
        cells: list[str] = [f"<td><code>{html.escape(c)}</code></td>"]

        def td_time(val: float | None, best: float | None) -> str:
            if val is None or not (val == val) or val <= 0:
                return "<td>—</td>"
            cls = ""
            if best is not None and val == best:
                cls = ' class="best"'
            return f"<td{cls}>{html.escape(_fmt_time(val))}</td>"

        em = enc_r.get(c)
        dm = dec_r.get(c)
        rm = rt_r.get(c)
        cells.append(td_time(em, enc_best))
        cells.append(td_time(dm, dec_best))
        cells.append(td_time(rm, rt_best))

        if has_wire:
            wv = wire_vals.get(c)
            if wv is not None:
                is_best = wire_best is not None and wv == wire_best
                cls = ' class="best"' if is_best else ""
                cells.append(f"<td{cls}>{html.escape(f'{wv:.0f}')}</td>")
            else:
                cells.append("<td>—</td>")

        if has_s1:
            sv = s1_vals.get(c)
            if sv is not None:
                is_best = s1_best is not None and sv == s1_best
                cls = ' class="best"' if is_best else ""
                cells.append(f"<td{cls}>{html.escape(str(sv))}</td>")
            else:
                cells.append("<td>—</td>")

        if has_s3:
            t3 = s3_vals.get(c)
            cells.append(td_time(t3, s3_best))

        if has_s4:
            t4 = s4_vals.get(c)
            cells.append(td_time(t4, s4_best))

        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return (
        '<table class="matrix"><thead>'
        f"{thead}</thead><tbody>{''.join(body_rows)}</tbody></table>"
        '<p class="fineprint"><strong>Best</strong> per column is highlighted. '
        "Timings are mean wall time per iteration from <code>report.json</code>; "
        "S3/S4 batch columns are separate from single-record encode/decode rows.</p>"
    )


def _section_for_group(tier: str, profile: str, rows: list[dict[str, Any]]) -> str:
    h = html.escape(f"{tier} · {profile}")
    if len(rows) < 2:
        c = html.escape(_codec(rows[0]) if rows else "?")
        inner = f"<p>Only <code>{c}</code> in this slice; "
        inner += "add formats to compare codecs.</p>"
    else:
        paras: list[str] = []
        for label, key in (
            ("encode", "encode"),
            ("decode", "decode"),
            ("round-trip", "round_trip"),
        ):
            ranked = _rank_by_mean(rows, key)
            sent = _winner_loser_sentence(label, ranked)
            if sent:
                paras.append(f"<p>{sent}</p>")
        if not paras:
            paras.append(
                "<p>No strong spread (&lt; "
                f"{_SPREAD_NOTE_RATIO:.2f}×) between fastest and slowest codec on "
                "encode, decode, or round-trip—treat differences as "
                "noise-sensitive.</p>",
            )
        inner = "".join(paras) + _comparison_table(rows)

    return f'<section class="tier-block"><h2>{h}</h2>{inner}</section>'


_SUMMARY_PAGE_CSS = """
<style>
body {
  font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  margin: 1.5rem;
  max-width: 56rem;
  color: #1a1a1a;
}
h1 { font-size: 1.35rem; }
h2 { font-size: 1.05rem; margin-top: 1.25rem; }
.meta { font-size: 0.9rem; line-height: 1.5; }
.cfg-pre {
  font-size: 0.78rem;
  max-height: 14rem;
  overflow: auto;
  background: #fff;
  border: 1px solid #ddd;
  padding: 0.5rem;
  margin: 0.35rem 0;
}
.intro ul { margin: 0.5rem 0 0 1rem; line-height: 1.5; }
.tier-block {
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
  margin-top: 0.75rem;
}
.matrix th, .matrix td {
  border: 1px solid #ccc;
  padding: 0.35rem 0.5rem;
  text-align: left;
}
.matrix th { background: #e8eef5; }
.matrix td.best { background: #e6f4ea; font-weight: 600; }
.win-rate {
  margin: 1rem 0 1.25rem;
  padding: 0.75rem 1rem 1rem;
  border-radius: 8px;
  border: 1px solid #c5d4e8;
  background: #f4f8fc;
}
.win-rate-table td.num {
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.fineprint {
  font-size: 0.78rem;
  color: #444;
  margin: 0.5rem 0 0;
  line-height: 1.4;
}
.caveats {
  margin-top: 1.5rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  border: 1px solid #d8e0ea;
  background: #f6f8fb;
}
.callout.warn {
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  border: 1px solid #c9a227;
  background: #fffbeb;
}
.callout.warn h2 { margin-top: 0; font-size: 1rem; }
.kafka-e2e {
  margin: 1rem 0 1.25rem;
  padding: 0.75rem 1rem 1rem;
  border-radius: 8px;
  border: 1px solid #c9c9c9;
  background: #faf8f5;
}
.page-nav {
  margin: 0 0 0.75rem;
  font-size: 0.92rem;
}
.page-nav a { color: #1e5a8a; }
.page-nav a:focus-visible { outline: 2px solid #2d6a9f; outline-offset: 2px; }
.ai-handoff {
  margin-top: 2rem;
  padding: 0.75rem 1rem 1rem;
  border-radius: 8px;
  border: 1px solid #c5d4e8;
  background: #f8fafc;
}
.ai-handoff details { margin-top: 0.5rem; }
.ai-handoff summary {
  cursor: pointer;
  font-weight: 600;
  color: #1e5a8a;
}
.ai-handoff-pre {
  margin: 0.75rem 0 0;
  padding: 0.75rem 1rem;
  max-height: 28rem;
  overflow: auto;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fff;
  border: 1px solid #d8e0ea;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
</style>
""".strip()


def build_summary_html(
    report: dict[str, Any],
    *,
    companion_stack_href: str | None = None,
    companion_distributed_href: str | None = None,
    viz_nav_html: str | None = None,
) -> str:
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
    rows = [r for r in raw_results if isinstance(r, dict)]
    groups = _group_rows(rows)

    scen_profiles_raw = profiles if isinstance(profiles, list) else []
    scen_profiles = [p for p in scen_profiles_raw if p is not None]

    sections: list[str] = []
    for t in TIER_ORDER:
        tier_rows = [r for r in rows if _tier(r) == t]
        if not tier_rows:
            continue
        for prof in _profile_order(scen_profiles, tier_rows):
            g = groups.get((t, prof))
            if g:
                sections.append(_section_for_group(t, prof, g))
    for (t, prof), g in sorted(
        groups.items(),
        key=lambda kv: (_tier_sort_key(kv[0][0]), kv[0][1]),
    ):
        if t in TIER_ORDER:
            continue
        sections.append(_section_for_group(t, prof, g))

    kafka_html = _kafka_e2e_section(report)
    handoff = _test_suite_ai_handoff_section()
    if not sections:
        body = kafka_html + "<p>No results in report.</p>" + handoff
    else:
        bullets = _collect_headline_bullets(groups)
        if companion_stack_href:
            eh = html.escape(companion_stack_href, quote=True)
            stack_blurb = (
                "<p>Each table compares codecs for the same benchmark tier and "
                f'payload profile. Open the <a href="{eh}">stack &amp; data view</a> '
                "for per-codec diagrams and bar charts."
            )
            if companion_distributed_href:
                dh = html.escape(companion_distributed_href, quote=True)
                stack_blurb += (
                    " For wire and timed-compression footprint, see "
                    f'<a href="{dh}">distributed footprint</a>.'
                )
            stack_blurb += "</p>"
        else:
            stack_blurb = (
                "<p>Each table compares codecs for the same benchmark tier and payload "
                "profile. Open the stack visualization for per-codec diagrams and bar "
                "charts.</p>"
            )
        body = (
            kafka_html
            + _win_rate_section(groups, rows)
            + '<section class="intro"><h2>Headlines</h2><ul>'
            f'{"".join(bullets)}</ul>'
            f"{stack_blurb}"
            "</section>"
            + _regression_block(report)
            + "".join(sections)
            + _limitations_block(report)
            + handoff
        )

    summary = (
        f"<p><strong>Scenario tier:</strong> {tier} &nbsp;|&nbsp; "
        f"<strong>Profiles:</strong> {prof_txt} &nbsp;|&nbsp; "
        f"<strong>Formats:</strong> {fmt_txt} &nbsp;|&nbsp; "
        f"<strong>Compression (scenario / S1 timed):</strong> {comp_txt} &nbsp;|&nbsp; "
        f"<strong>Timed iterations:</strong> {html.escape(str(iters))} &nbsp;|&nbsp; "
        f"<code>report_version</code> {html.escape(str(ver))}</p>"
    )

    if viz_nav_html is not None:
        nav = viz_nav_html
    elif companion_stack_href or companion_distributed_href:
        nav = companion_viz_nav_html(
            stack_href=companion_stack_href,
            summary_href="",
            distributed_href=companion_distributed_href,
            current="summary",
        )
    else:
        nav = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Performance summary — ksp-bench report</title>
{_SUMMARY_PAGE_CSS}
</head>
<body>
{nav}
<h1>Performance summary</h1>
{summary}
{body}
</body>
</html>
"""


def write_summary_visualization(
    report_path: str | Path,
    output_path: str | Path,
    *,
    companion_stack_path: Path | None = None,
    companion_distributed_path: Path | None = None,
) -> None:
    rp = Path(report_path)
    with rp.open(encoding="utf-8") as f:
        report = cast(dict[str, Any], json.load(f))
    op = Path(output_path)
    stack_p = Path(companion_stack_path) if companion_stack_path is not None else None
    dist_p = (
        Path(companion_distributed_path)
        if companion_distributed_path is not None
        else None
    )
    nav = ""
    if stack_p is not None:
        nav = build_viz_sibling_nav_html(
            current_html=op,
            stack_output=stack_p,
            summary_output=op,
            distributed_output=dist_p,
            current="summary",
        )
    dist_href: str | None = None
    if stack_p is not None and dist_p is not None:
        dist_href = relative_viz_href(from_html=op, to_html=dist_p)
    stack_href: str | None = None
    if stack_p is not None:
        stack_href = relative_viz_href(from_html=op, to_html=stack_p)
    html_out = build_summary_html(
        report,
        companion_stack_href=stack_href,
        companion_distributed_href=dist_href,
        viz_nav_html=nav if nav else None,
    )
    op.parent.mkdir(parents=True, exist_ok=True)
    with op.open("w", encoding="utf-8") as f:
        f.write(html_out)
