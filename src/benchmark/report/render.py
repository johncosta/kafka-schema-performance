from __future__ import annotations

import math
from itertools import groupby
from typing import Any


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
    if "governance_rubric" in report:
        lines.append("## Governance rubric (metadata)")
        lines.append("")
        lines.append("See `report.json` for the versioned YAML payload.")
        lines.append("")
    return "\n".join(lines)
