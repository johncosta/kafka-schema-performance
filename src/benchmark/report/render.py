from __future__ import annotations

from typing import Any


def render_markdown(report: dict[str, Any]) -> str:
    scen = report["scenario"]
    lines = [
        "# Serialization benchmark report",
        "",
        "## Scenario",
        "",
        f"- **Payload profile:** {scen['payload_profile']}",
        f"- **Tier:** {scen['tier']} (see layer cake per result)",
        f"- **Formats:** {', '.join(scen['formats'])}",
        f"- **Timed iterations:** {scen['timed_iterations']} "
        f"(warmup {scen['warmup_iterations']})",
        f"- **Seed:** {scen['seed']}",
        "",
        "## Environment",
        "",
        "```",
        str(report["environment"]),
        "```",
        "",
        f"**Fixture bundle SHA256:** `{report['fixture_bundle_sha256']}`",
        "",
        "## Results",
        "",
    ]
    for row in report["results"]:
        lines.extend(
            [
                f"### {row['codec']}",
                "",
                f"- Raw size (bytes): {row['raw_size_bytes']}",
                f"- Compressed size (bytes): {row['compressed_size_bytes']}",
                f"- Encode mean (s): {row['encode']['mean_s']:.6e}",
                f"- Decode mean (s): {row['decode']['mean_s']:.6e}",
                f"- Round-trip mean (s): {row['round_trip']['mean_s']:.6e}",
                f"- Encode p99 (s): {row['encode']['p99_s']:.6e}",
                f"- Records/s encode: {row['encode']['records_per_s']:,.0f}",
                f"- Encode MB/s: {row['encode']['encode_mb_per_s']:.2f}",
                "",
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
