from __future__ import annotations

import math
from itertools import groupby
from typing import Any

from benchmark.report.rubrics_md import append_rubric_appendix


def append_phase8_sections(lines: list[str], report: dict[str, Any]) -> None:
    """Limitations, pip-freeze digest, optional regression block (Phase 8)."""

    lim = report.get("limitations")
    if isinstance(lim, dict):
        lines.extend(["---", "", "## Limitations", ""])
        summ = lim.get("summary")
        if summ:
            lines.append(str(summ))
            lines.append("")
        pts = lim.get("points")
        if isinstance(pts, list):
            for p in pts:
                lines.append(f"- {p}")
            lines.append("")
        pol = lim.get("interpretation_policy")
        if pol:
            lines.append(f"**Interpretation:** {pol}")
            lines.append("")
        cov = lim.get("evidence_coverage")
        if isinstance(cov, dict):
            lines.extend(["### Evidence coverage (PRD §6.6)", ""])
            cs = cov.get("summary")
            if cs:
                lines.append(str(cs))
                lines.append("")
            nm = cov.get("not_measured")
            if isinstance(nm, list) and nm:
                lines.append("**Not measured (do not infer from this report alone):**")
                for item in nm:
                    lines.append(f"- {item}")
                lines.append("")
            tc = cov.get("test_and_ci")
            if tc:
                lines.append(f"**Tests / CI:** {tc}")
                lines.append("")

    art = report.get("artifact_integrity")
    if isinstance(art, dict):
        lines.extend(["## Artifact integrity", ""])
        if art.get("error"):
            lines.append(f"- Capture failed: {art['error']}")
        else:
            lines.append(f"- Method: {art.get('method', '')}")
            lines.append(f"- Sorted `pip freeze` lines: {art.get('line_count', 0)}")
            sha = art.get("sha256", "")
            lines.append(
                f"- SHA-256 (UTF-8, sorted lines joined by newlines): `{sha}`",
            )
            ec = art.get("pip_exit_code")
            if ec not in (None, 0):
                lines.append(f"- `pip` exit code: {ec}")
        note = art.get("note")
        if note:
            lines.append(f"- {note}")
        lines.append("")

    rc = report.get("regression_check")
    if isinstance(rc, dict):
        lines.extend(["## Regression check (optional)", ""])
        if rc.get("skipped"):
            lines.append(f"Skipped: {rc.get('reason', '')}")
            bp = rc.get("baseline_path")
            if bp:
                lines.append(f"Baseline: `{bp}`")
        else:
            bp = rc.get("baseline_path")
            if bp:
                lines.append(f"Baseline: `{bp}`")
            wr = rc.get("warn_ratio")
            if wr is not None:
                lines.append(f"Warn ratio: {wr}")
            warns = rc.get("warnings") or []
            if not warns:
                lines.append("No warnings (within threshold).")
            else:
                for w in warns:
                    if isinstance(w, dict) and w.get("message"):
                        lines.append(f"- {w['message']}")
                    else:
                        lines.append(f"- {w}")
            note = rc.get("note")
            if note:
                lines.append("")
                lines.append(f"_{note}_")
        lines.append("")


def _fmt_sci(x: float) -> str:
    if math.isnan(x):
        return "nan"
    return f"{x:.6e}"


def _dict_mean_s(block: object) -> float:
    if isinstance(block, dict):
        return float(block.get("mean_s", float("nan")))
    return float("nan")


def _fmt_intish(x: float) -> str:
    if math.isnan(x):
        return "nan"
    return f"{x:,.0f}"


def _fmt_mb_s(x: float) -> str:
    if math.isnan(x):
        return "nan"
    return f"{x:.2f}"


def _fmt_ratio(x: float) -> str:
    if math.isnan(x):
        return "nan"
    return f"{x:.3f}"


def append_kafka_e2e_markdown(lines: list[str], report: dict[str, Any]) -> None:
    """Append optional broker-backed block when ``kafka_e2e`` is present."""

    ke = report.get("kafka_e2e")
    if not isinstance(ke, dict):
        return
    lines.extend(["---", "", "## Kafka-protocol end-to-end (`kafka_e2e`)", ""])
    lines.append(f"- **kafka_e2e_version:** {ke.get('kafka_e2e_version', '?')}")
    lines.append(f"- **Bootstrap:** `{ke.get('bootstrap_servers', '?')}`")
    lines.append(f"- **Broker label:** {ke.get('broker_implementation', '?')}")
    cli = ke.get("client")
    if isinstance(cli, dict):
        lib = cli.get("library", "?")
        av = cli.get("api_version", "?")
        lines.append(f"- **Client library:** {lib} (api_version={av})")
    pc = ke.get("producer_config")
    if isinstance(pc, dict):
        lines.append(f"- **Producer config (snapshot):** `{pc}`")
    cc = ke.get("consumer_config")
    if isinstance(cc, dict):
        lines.append(f"- **Consumer config (snapshot):** `{cc}`")
    phases = ke.get("phases")
    if isinstance(phases, dict) and phases:
        lines.append("")
        lines.append("**Phase definitions:**")
        for k, v in phases.items():
            if isinstance(v, str):
                lines.append(f"- **{k}:** {v}")
    rm = ke.get("roadmap")
    if isinstance(rm, str) and rm.strip():
        lines.extend(["", f"**Roadmap (normative target, PRD §6.3.1):** {rm}"])
    cases = ke.get("cases")
    if not isinstance(cases, list) or not cases:
        lines.append("")
        return
    lines.extend(["", "### Per-codec cases", ""])
    for c in cases:
        if not isinstance(c, dict):
            continue
        codec = c.get("codec", "?")
        prof = c.get("payload_profile", "?")
        vb = c.get("value_bytes", "?")
        lines.append(f"- **`{codec}` / `{prof}`:** value {vb} B")
        ser = c.get("serialize")
        if isinstance(ser, dict):
            ms = ser.get("mean_s")
            if isinstance(ms, (int, float)) and ms == ms:
                lines.append(f"  - Serialize mean: {_fmt_sci(float(ms))} s")
        pr = c.get("produce")
        if isinstance(pr, dict):
            mpm = pr.get("mean_per_message_s")
            tps = pr.get("throughput_messages_per_s")
            tmbs = pr.get("throughput_megabytes_per_s")
            bits: list[str] = []
            if isinstance(mpm, (int, float)) and mpm == mpm:
                bits.append(f"produce mean/msg {_fmt_sci(float(mpm))} s")
            if isinstance(tps, (int, float)) and tps == tps:
                bits.append(f"{float(tps):,.1f} msg/s")
            if isinstance(tmbs, (int, float)) and tmbs == tmbs:
                bits.append(f"{_fmt_mb_s(float(tmbs))} MB/s")
            if bits:
                lines.append(f"  - Timed produce: {', '.join(bits)}")
        co = c.get("consume")
        if isinstance(co, dict):
            mpm = co.get("mean_per_message_s")
            tps = co.get("throughput_messages_per_s")
            tmbs = co.get("throughput_megabytes_per_s")
            bits = []
            if isinstance(mpm, (int, float)) and mpm == mpm:
                bits.append(f"consume mean/msg {_fmt_sci(float(mpm))} s")
            if isinstance(tps, (int, float)) and tps == tps:
                bits.append(f"{float(tps):,.1f} msg/s")
            if isinstance(tmbs, (int, float)) and tmbs == tmbs:
                bits.append(f"{_fmt_mb_s(float(tmbs))} MB/s")
            if bits:
                lines.append(f"  - Consume loop: {', '.join(bits)}")
    lines.append("")


def _scenario_profiles(scen: dict[str, Any]) -> list[str]:
    p = scen.get("payload_profiles")
    if isinstance(p, list) and p:
        return [str(x) for x in p]
    legacy = scen.get("payload_profile")
    if legacy is not None:
        return [str(legacy)]
    return ["unknown"]


def render_markdown(report: dict[str, Any]) -> str:
    scen = report["scenario"]
    profile_labels = _scenario_profiles(scen)
    lines = [
        "# Serialization benchmark report",
        "",
        "## Scenario",
        "",
        f"- **Payload profile(s):** {', '.join(profile_labels)}",
        f"- **Tier:** {scen['tier']} (see layer cake per result)",
    ]
    te = scen.get("tiers_executed")
    if isinstance(te, list) and te:
        joined = ", ".join(str(x) for x in te)
        lines.append(f"- **Tiers executed (single report):** {joined}")
        lines.append("")
    lines.extend(
        [
            f"- **Formats:** {', '.join(scen['formats'])}",
            f"- **Timed iterations:** {scen['timed_iterations']} "
            f"(warmup {scen['warmup_iterations']})",
            f"- **Seed:** {scen['seed']}",
            "",
        ],
    )
    if scen.get("batch_size") is not None:
        lines.append(f"- **Batch size:** {scen['batch_size']}")
        lines.append("")
    s1_scen = scen.get("s1")
    if isinstance(s1_scen, dict) and scen.get("tier") in ("S1", "all"):
        lines.extend(
            [
                "### Tier S1 (codec + compression)",
                "",
                "- **Timed compression algorithm:** "
                f"{s1_scen.get('timed_compression_algorithm')}",
                "- **S1 gzip level (CLI / default):** "
                f"{s1_scen.get('gzip_level_cli')} / "
                f"{s1_scen.get('default_gzip_level')}",
                "- **S1 zstd level (CLI / default):** "
                f"{s1_scen.get('zstd_level_cli')} / "
                f"{s1_scen.get('default_zstd_level')}",
                f"- **Note:** {s1_scen.get('note', '')}",
                "",
                "*Compare to S0: re-run with `--tier S0` and the same profiles/seed.*",
                "",
            ]
        )
    s2_scen = scen.get("s2")
    if isinstance(s2_scen, dict) and scen.get("tier") in ("S2", "all"):
        lines.extend(
            [
                "### Tier S2 (codec + mock schema registry)",
                "",
                f"- **Registry:** {s2_scen.get('registry_implementation')} on "
                f"{s2_scen.get('bind')}",
                f"- **Schema id:** {s2_scen.get('schema_id')}",
                f"- **API:** {s2_scen.get('api')}",
                f"- **Note:** {s2_scen.get('note', '')}",
                "",
                "*Cold vs warm fetch timings appear per codec row "
                "under **S2 registry**.*",
                "",
            ]
        )
    s34 = scen.get("s3_s4")
    t34 = scen.get("tier")
    if isinstance(s34, dict) and t34 in ("S3", "all"):
        lines.extend(
            [
                "### Tier S3 (memory producer batch)",
                "",
                f"- **Batch size:** {s34.get('batch_size')}",
                f"- **Implementation:** {s34.get('implementation')}",
                f"- **Note:** {s34.get('note', '')}",
                "",
            ]
        )
    if isinstance(s34, dict) and t34 in ("S4", "all"):
        lines.extend(
            [
                "### Tier S4 (memory consumer batch)",
                "",
                f"- **Batch size:** {s34.get('batch_size')}",
                f"- **Implementation:** {s34.get('implementation')}",
                f"- **Note:** {s34.get('note', '')}",
                "",
            ]
        )
    sz = scen.get("size_and_cost")
    if isinstance(sz, dict):
        lines.extend(
            [
                "### Size & cost settings",
                "",
                f"- **gzip compresslevel (size probe):** "
                f"{sz.get('gzip_compresslevel')}",
                f"- **zstd level (size probe):** {sz.get('zstd_level')}",
                f"- **Confluent value prefix in report:** "
                f"{sz.get('include_confluent_envelope')}",
                "",
            ]
        )
    meas = report.get("measurement")
    if meas:
        lines.extend(
            [
                "## Measurement model",
                "",
                f"- **Timer:** {meas.get('timer', '')}",
                f"- **Threading:** {meas.get('threading_model', '')}",
                "",
            ]
        )
        phases = meas.get("phases")
        if isinstance(phases, dict):
            lines.append("**Phases (fine-grained timing boundaries):**")
            lines.append("")
            for name, desc in phases.items():
                lines.append(f"- **{name}:** {desc}")
            lines.append("")
        tier_note = meas.get("tier_s1_vs_s0")
        if isinstance(tier_note, str) and tier_note:
            lines.append("**S0 vs S1:**")
            lines.append("")
            lines.append(tier_note)
            lines.append("")
        tier_s2 = meas.get("tier_s2_registry")
        if isinstance(tier_s2, str) and tier_s2:
            lines.append("**S2 (registry):**")
            lines.append("")
            lines.append(tier_s2)
            lines.append("")
        tier_s34 = meas.get("tier_s3_s4_memory")
        if isinstance(tier_s34, str) and tier_s34:
            lines.append("**S3/S4 (memory queue):**")
            lines.append("")
            lines.append(tier_s34)
            lines.append("")
    lines.extend(
        [
            "## Environment",
            "",
            "```",
            str(report["environment"]),
            "```",
            "",
            f"**Fixture bundle SHA256:** `{report['fixture_bundle_sha256']}`",
            "",
        ]
    )
    results = list(report["results"])
    results.sort(
        key=lambda r: (
            str(r.get("payload_profile", "")),
            str(r.get("codec", "")),
            str(r.get("tier", "")),
        ),
    )

    lines.append("## Results")
    lines.append("")

    def _profile_key(row: dict[str, Any]) -> str:
        return str(row.get("payload_profile", profile_labels[0]))

    for profile, group in groupby(results, key=_profile_key):
        lines.append(f"### Profile `{profile}`")
        lines.append("")
        for row in group:
            enc = row["encode"]
            dec = row["decode"]
            rt = row["round_trip"]
            tier_lbl = str(row.get("tier", ""))
            tier_suffix = f" — `{tier_lbl}`" if tier_lbl else ""
            lines.extend(
                [
                    f"#### {row['codec']}{tier_suffix}",
                    "",
                    f"- Raw size (bytes): {row['raw_size_bytes']}",
                    f"- Compressed size (bytes): {row['compressed_size_bytes']}",
                    "",
                    "**Encode:**",
                    f"- mean: {_fmt_sci(enc['mean_s'])} s | "
                    f"p50 / p90 / p99: {_fmt_sci(enc['p50_s'])} / "
                    f"{_fmt_sci(enc['p90_s'])} / {_fmt_sci(enc['p99_s'])}",
                    f"- records/s: {_fmt_intish(enc['records_per_s'])} | "
                    f"MB/s (raw wire): {_fmt_mb_s(enc['encode_mb_per_s'])}",
                    "",
                ]
            )
            if "encode_compressed_wire_mb_per_s" in enc:
                lines.append(
                    f"- **S1** MB/s on compressed wire (encode+compress): "
                    f"{_fmt_mb_s(enc['encode_compressed_wire_mb_per_s'])}",
                )
                lines.append("")
            lines.extend(
                [
                    "**Decode:**",
                    f"- mean: {_fmt_sci(dec['mean_s'])} s | "
                    f"p50 / p90 / p99: {_fmt_sci(dec['p50_s'])} / "
                    f"{_fmt_sci(dec['p90_s'])} / {_fmt_sci(dec['p99_s'])}",
                    f"- records/s: {_fmt_intish(dec['records_per_s'])} | "
                    f"MB/s (raw wire): {_fmt_mb_s(dec['decode_mb_per_s'])}",
                    "",
                ]
            )
            if "decode_compressed_input_mb_per_s" in dec:
                lines.append(
                    f"- **S1** MB/s reading compressed bytes (decompress+decode): "
                    f"{_fmt_mb_s(dec['decode_compressed_input_mb_per_s'])}",
                )
                lines.append("")
            lines.extend(
                [
                    "**Round-trip:**",
                    f"- mean: {_fmt_sci(rt['mean_s'])} s | "
                    f"p50 / p90 / p99: {_fmt_sci(rt['p50_s'])} / "
                    f"{_fmt_sci(rt['p90_s'])} / {_fmt_sci(rt['p99_s'])}",
                    f"- records/s: {_fmt_intish(rt['records_per_s'])} | "
                    f"MB/s (raw wire): "
                    f"{_fmt_mb_s(rt.get('round_trip_mb_per_s', float('nan')))}",
                    "",
                ]
            )
            if "round_trip_compressed_wire_mb_per_s" in rt:
                lines.append(
                    f"- **S1** MB/s on compressed wire (full round-trip path): "
                    f"{_fmt_mb_s(rt['round_trip_compressed_wire_mb_per_s'])}",
                )
                lines.append("")
            s3b = row.get("s3_producer_batch")
            if isinstance(s3b, dict):
                bb = s3b.get("batch_build_and_join")
                if isinstance(bb, dict):
                    m = _fmt_sci(float(bb.get("mean_s", float("nan"))))
                    rps = s3b.get("effective_records_per_s")
                    rps_f = (
                        float(rps) if isinstance(rps, (int, float)) else float("nan")
                    )
                    mb3 = _fmt_mb_s(
                        float(s3b.get("batch_mb_per_s", float("nan"))),
                    )
                    lines.extend(
                        [
                            "**S3 producer batch (memory, no broker):**",
                            "",
                            f"- batch_size: {s3b.get('batch_size')}",
                            f"- batch mean time: {m} s",
                            f"- batch MB/s: {mb3}",
                            f"- effective records/s (batch): {_fmt_intish(rps_f)}",
                            f"- *{s3b.get('note', '')}*",
                            "",
                        ]
                    )
            s4b = row.get("s4_consumer_batch")
            if isinstance(s4b, dict):
                bd = s4b.get("batch_decode")
                if isinstance(bd, dict):
                    m = _fmt_sci(float(bd.get("mean_s", float("nan"))))
                    rps = s4b.get("effective_records_per_s")
                    rps_f = (
                        float(rps) if isinstance(rps, (int, float)) else float("nan")
                    )
                    mb4 = _fmt_mb_s(
                        float(s4b.get("batch_mb_per_s", float("nan"))),
                    )
                    lines.extend(
                        [
                            "**S4 consumer batch (memory, no broker):**",
                            "",
                            f"- batch_size: {s4b.get('batch_size')}",
                            f"- batch decode mean time: {m} s",
                            f"- batch MB/s: {mb4}",
                            f"- effective records/s (batch): {_fmt_intish(rps_f)}",
                            f"- *Prefetch:* {s4b.get('prefetch_note', '')}",
                            f"- *{s4b.get('note', '')}*",
                            "",
                        ]
                    )
            s2r = row.get("s2_registry")
            if isinstance(s2r, dict):
                fc = s2r.get("fetch_new_tcp_each_iteration")
                fw = s2r.get("fetch_reused_connection")
                if isinstance(fc, dict) and isinstance(fw, dict):
                    cold_m = _fmt_sci(float(fc.get("mean_s", float("nan"))))
                    warm_m = _fmt_sci(float(fw.get("mean_s", float("nan"))))
                    lines.extend(
                        [
                            "**S2 registry (loopback mock):**",
                            "",
                            f"- Fetch cold (new TCP each): mean {cold_m} s",
                            f"- Fetch warm (reuse connection): mean {warm_m} s",
                            f"- *{s2r.get('note', '')}*",
                            "",
                        ]
                    )
            s1c = row.get("s1_timed_compression")
            if isinstance(s1c, dict):
                ratio = s1c.get("ratio_compressed_to_raw")
                if isinstance(ratio, float) and math.isnan(ratio):
                    rtxt = "nan"
                elif isinstance(ratio, (int, float)):
                    rtxt = f"{float(ratio):.4f}"
                else:
                    rtxt = str(ratio)
                lines.extend(
                    [
                        "**S1 compression footprint (timed path):**",
                        "",
                        f"- Algorithm: `{s1c.get('timed_algorithm')}` | "
                        f"compressed/raw ratio: {rtxt}",
                        f"- Raw {s1c.get('raw_bytes')} B → compressed "
                        f"{s1c.get('compressed_bytes')} B",
                        f"- *{s1c.get('note', '')}*",
                        "",
                    ]
                )
            s1p = row.get("s1_phase_isolation")
            if isinstance(s1p, dict):
                dr = _fmt_sci(_dict_mean_s(s1p.get("codec_decode_raw_wire_s")))
                lines.extend(
                    [
                        "**S1 phase isolation (PRD §6.6.1):**",
                        "",
                        f"- Compress wire only: mean "
                        f"{_fmt_sci(_dict_mean_s(s1p.get('compress_wire_s')))} s",
                        f"- Decompress wire only: mean "
                        f"{_fmt_sci(_dict_mean_s(s1p.get('decompress_wire_s')))} s",
                        f"- Codec encode only: mean "
                        f"{_fmt_sci(_dict_mean_s(s1p.get('codec_encode_only_s')))} s",
                        f"- Codec decode (raw wire, no decompress): mean {dr} s",
                        f"- *{s1p.get('note', '')}*",
                        "",
                    ]
                )
            raw_enc = row.get("raw_encoded_bytes")
            if isinstance(raw_enc, dict) and raw_enc.get("n"):
                lines.extend(
                    [
                        "**Raw encoded size (per timed encode):**",
                        f"- mean / median / p95 (bytes): "
                        f"{float(raw_enc['mean']):.1f} / "
                        f"{float(raw_enc['median']):.1f} / "
                        f"{float(raw_enc['p95']):.1f} (n={raw_enc['n']})",
                        "",
                    ]
                )
            cp = row.get("compressed_payload_bytes")
            if isinstance(cp, dict):
                gz = cp.get("gzip")
                zst = cp.get("zstd")
                if isinstance(gz, dict) and isinstance(zst, dict):
                    gz_ratio = _fmt_ratio(
                        float(gz.get("ratio_to_raw_mean", float("nan"))),
                    )
                    zs_ratio = _fmt_ratio(
                        float(zst.get("ratio_to_raw_mean", float("nan"))),
                    )
                    lines.extend(
                        [
                            "**Compressed payload sizes (full raw wire):**",
                            f"- gzip (level {gz.get('compresslevel')}): "
                            f"{gz.get('bytes')} B (ratio× raw mean {gz_ratio})",
                            f"- zstd (level {zst.get('level')}): "
                            f"{zst.get('bytes')} B (ratio× raw mean {zs_ratio})",
                            "",
                        ]
                    )
            ks = row.get("kafka_shaped")
            if isinstance(ks, dict):
                lines.extend(
                    [
                        "**Kafka-shaped value (Confluent prefix + payload):**",
                        f"- {ks.get('total_value_bytes')} B total "
                        f"({ks.get('prefix_bytes')} B prefix + "
                        f"{ks.get('payload_bytes')} B payload)",
                        "",
                    ]
                )
            dc = row.get("derived_cost")
            if isinstance(dc, dict):
                lines.append("**Derived cost (illustrative, PRD section 6.2):**")
                lines.append("")
                rf = dc.get("reference_formulas")
                if isinstance(rf, dict):
                    for k, v in rf.items():
                        lines.append(f"- `{k}`: {v}")
                span = dc.get("illustrative_mean_wire_bytes_span")
                if isinstance(span, dict):
                    low = float(span.get("low", float("nan")))
                    high = float(span.get("high", float("nan")))
                    pct = dc.get("sensitivity_payload_plus_minus_pct", 20)
                    lines.append(
                        f"- ±{pct}% mean-wire span (bytes): {low:.1f} … {high:.1f}"
                    )
                note = dc.get("notes")
                if note:
                    lines.append(f"- Note: {note}")
                lines.append("")
            alloc = row.get("allocations")
            if alloc:
                lines.append("**Allocations (best-effort):**")
                lines.append("")
                lines.append(f"- Peak bytes (traced): {alloc.get('peak_bytes_traced')}")
                lines.append(f"- Note: {alloc.get('caveat', '')}")
                lines.append("")
            lines.extend(
                [
                    "**Layer cake:**",
                    "",
                ]
            )
            lc = row["layer_cake"]
            lines.append(f"- Included: {', '.join(lc['included'])}")
            lines.append(f"- Excluded: {', '.join(lc['excluded'])}")
            lines.append("")
    append_kafka_e2e_markdown(lines, report)
    append_rubric_appendix(lines, report)
    append_phase8_sections(lines, report)
    return "\n".join(lines)
