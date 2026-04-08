from __future__ import annotations

import math
from itertools import groupby
from typing import Any

from benchmark.report.rubrics_md import append_rubric_appendix


def _fmt_sci(x: float) -> str:
    if math.isnan(x):
        return "nan"
    return f"{x:.6e}"


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
        f"- **Formats:** {', '.join(scen['formats'])}",
        f"- **Timed iterations:** {scen['timed_iterations']} "
        f"(warmup {scen['warmup_iterations']})",
        f"- **Seed:** {scen['seed']}",
        "",
    ]
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
    results.sort(key=lambda r: (r.get("payload_profile", ""), r.get("codec", "")))

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
            lines.extend(
                [
                    f"#### {row['codec']}",
                    "",
                    f"- Raw size (bytes): {row['raw_size_bytes']}",
                    f"- Compressed size (bytes): {row['compressed_size_bytes']}",
                    "",
                    "**Encode:**",
                    f"- mean: {_fmt_sci(enc['mean_s'])} s | "
                    f"p50 / p90 / p99: {_fmt_sci(enc['p50_s'])} / "
                    f"{_fmt_sci(enc['p90_s'])} / {_fmt_sci(enc['p99_s'])}",
                    f"- records/s: {_fmt_intish(enc['records_per_s'])} | "
                    f"MB/s: {_fmt_mb_s(enc['encode_mb_per_s'])}",
                    "",
                    "**Decode:**",
                    f"- mean: {_fmt_sci(dec['mean_s'])} s | "
                    f"p50 / p90 / p99: {_fmt_sci(dec['p50_s'])} / "
                    f"{_fmt_sci(dec['p90_s'])} / {_fmt_sci(dec['p99_s'])}",
                    f"- records/s: {_fmt_intish(dec['records_per_s'])} | "
                    f"MB/s: {_fmt_mb_s(dec['decode_mb_per_s'])}",
                    "",
                    "**Round-trip:**",
                    f"- mean: {_fmt_sci(rt['mean_s'])} s | "
                    f"p50 / p90 / p99: {_fmt_sci(rt['p50_s'])} / "
                    f"{_fmt_sci(rt['p90_s'])} / {_fmt_sci(rt['p99_s'])}",
                    f"- records/s: {_fmt_intish(rt['records_per_s'])} | "
                    f"MB/s: {_fmt_mb_s(rt.get('round_trip_mb_per_s', float('nan')))}",
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
    append_rubric_appendix(lines, report)
    return "\n".join(lines)
