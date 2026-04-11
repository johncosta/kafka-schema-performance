from __future__ import annotations

from pathlib import Path

import typer

from benchmark.generate.records import PayloadProfile
from benchmark.scenarios.runner import (
    ReportTier,
    build_report,
    write_report_bundle,
)

app = typer.Typer(
    help="Kafka-schema-performance serialization benchmarks.",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Root command group (use the ``run`` subcommand)."""


def main() -> None:
    app()


def _parse_scenarios(value: str) -> list[PayloadProfile]:
    """One profile, comma-separated list, or ``all`` (= small+medium+large)."""

    raw = value.strip()
    if not raw:
        raise typer.BadParameter("scenario must not be empty")
    lowered = raw.lower()
    if lowered == "all":
        return [
            PayloadProfile.small,
            PayloadProfile.medium,
            PayloadProfile.large,
        ]
    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            raise typer.BadParameter("empty scenario list")
        try:
            return [PayloadProfile(p) for p in parts]
        except ValueError as e:
            raise typer.BadParameter(str(e)) from e
    try:
        return [PayloadProfile(raw)]
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


def _parse_formats(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return ["avro", "protobuf", "json"]
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    allowed = {"avro", "protobuf", "json"}
    bad = set(parts) - allowed
    if bad:
        raise typer.BadParameter(
            f"unknown formats: {bad}; use avro,protobuf,json or all",
        )
    if not parts:
        raise typer.BadParameter("at least one format required")
    return parts


@app.command("run")
def run_cmd(
    scenario: str = typer.Option(
        "small",
        "--scenario",
        "-s",
        help=(
            "Payload profile(s): small | medium | large | evolution | all "
            "(small+medium+large) | comma-separated list"
        ),
    ),
    tier: str = typer.Option(
        "S0",
        "--tier",
        "-t",
        help=(
            "S0 codec; S1 codec+compression; S2 mock schema registry; "
            "S3/S4 in-memory producer/consumer batch (no broker); "
            "all = one report with rows for every tier (S0→S4)"
        ),
    ),
    formats: str = typer.Option(
        "all",
        "--formats",
        "-f",
        help="Comma-separated avro,protobuf,json or 'all'",
    ),
    output_dir: Path = typer.Option(Path("reports"), "--output-dir", "-o"),
    warmup: int = typer.Option(100, "--warmup", min=0),
    iterations: int = typer.Option(1_000, "--iterations", "-n", min=1),
    seed: int = typer.Option(42, "--seed"),
    compression: str = typer.Option(
        "zstd",
        "--compression",
        help="gzip | zstd (used when tier=S1)",
    ),
    governance_rubric: Path | None = typer.Option(
        None,
        "--governance-rubric",
        help=(
            "Path to governance YAML "
            "(default: ./rubrics/governance.v1.yaml if present)"
        ),
    ),
    maintainability_rubric: Path | None = typer.Option(
        None,
        "--maintainability-rubric",
        help=(
            "Path to maintainability YAML "
            "(default: ./rubrics/maintainability.v1.yaml if present)"
        ),
    ),
    tracemalloc_sample: bool = typer.Option(
        False,
        "--tracemalloc/--no-tracemalloc",
        help="Optional one-shot tracemalloc peak after warmup (noisy; off by default)",
    ),
    gzip_level: int = typer.Option(
        6,
        "--gzip-level",
        min=1,
        max=9,
        help="gzip level used for wire-size probes (Phase 3; independent of tier S1)",
    ),
    zstd_level: int = typer.Option(
        3,
        "--zstd-level",
        min=1,
        max=22,
        help="zstd level used for wire-size probes (Phase 3; independent of tier S1)",
    ),
    confluent_envelope: bool = typer.Option(
        False,
        "--confluent-envelope/--no-confluent-envelope",
        help="Add Confluent wire-format value prefix bytes to kafka_shaped size",
    ),
    confluent_prefix_bytes: int = typer.Option(
        5,
        "--confluent-prefix-bytes",
        min=0,
        max=256,
        help="Prefix length for kafka_shaped total (default 5 = magic+schema id)",
    ),
    s1_gzip_level: int | None = typer.Option(
        None,
        "--s1-gzip-level",
        min=1,
        max=9,
        help="Tier S1 only: gzip level for timed compress (default 6 if omitted)",
    ),
    s1_zstd_level: int | None = typer.Option(
        None,
        "--s1-zstd-level",
        min=1,
        max=22,
        help="Tier S1 only: zstd level for timed compress (default 3 if omitted)",
    ),
    baseline_report: Path | None = typer.Option(
        None,
        "--baseline-report",
        help=(
            "Optional prior report.json for heuristic regression warnings "
            "(same scenario fingerprint required)"
        ),
    ),
    regression_warn_ratio: float = typer.Option(
        0.2,
        "--regression-warn-ratio",
        min=0.0,
        help="Warn if round_trip mean exceeds baseline × (1 + this ratio)",
    ),
    registry_schema_id: int = typer.Option(
        1,
        "--registry-schema-id",
        min=1,
        help="Tier S2 only: schema id for mock GET /schemas/ids/{id}",
    ),
    batch_size: int = typer.Option(
        64,
        "--batch-size",
        min=1,
        help="Tier S3/S4 only: records per timed batch iteration",
    ),
) -> None:
    """Run benchmark matrix and write report.json (+ report.md)."""

    profiles = _parse_scenarios(scenario)
    if tier not in ("S0", "S1", "S2", "S3", "S4", "all"):
        raise typer.BadParameter("tier must be S0, S1, S2, S3, S4, or all")
    tier_t: ReportTier = tier  # type: ignore[assignment]
    fmt_list = _parse_formats(formats)
    if tier in ("S0", "S2", "S3", "S4") and compression != "zstd":
        # allow but note compression unused for timed S0/S2/S3/S4 codec path
        pass
    comp: str = compression
    if comp not in ("gzip", "zstd"):
        raise typer.BadParameter(
            "compression must be gzip or zstd "
            "(S1 timed path; S0/S2/S3/S4 ignore for codec timing)",
        )

    gov = governance_rubric
    if gov is None:
        default_gov = Path("rubrics/governance.v1.yaml")
        if default_gov.is_file():
            gov = default_gov
    maint = maintainability_rubric
    if maint is None:
        default_m = Path("rubrics/maintainability.v1.yaml")
        if default_m.is_file():
            maint = default_m

    report = build_report(
        profiles=profiles,
        tier=tier_t,
        formats=fmt_list,
        compression=comp,  # type: ignore[arg-type]
        warmup=warmup,
        iterations=iterations,
        seed=seed,
        rubric_governance=str(gov) if gov else None,
        rubric_maintainability=str(maint) if maint else None,
        tracemalloc_sample=tracemalloc_sample,
        gzip_level=gzip_level,
        zstd_level=zstd_level,
        include_confluent_envelope=confluent_envelope,
        confluent_prefix_bytes=confluent_prefix_bytes,
        s1_gzip_level=s1_gzip_level,
        s1_zstd_level=s1_zstd_level,
        baseline_report_path=str(baseline_report) if baseline_report else None,
        regression_warn_ratio=regression_warn_ratio,
        registry_schema_id=registry_schema_id,
        batch_size=batch_size,
    )
    rc = report.get("regression_check")
    if isinstance(rc, dict) and not rc.get("skipped") and rc.get("warnings"):
        for w in rc["warnings"]:
            msg = w.get("message") if isinstance(w, dict) else str(w)
            typer.echo(msg, err=True)
    json_path, md_path = write_report_bundle(report, str(output_dir))
    typer.echo(f"Wrote {json_path}")
    if md_path:
        typer.echo(f"Wrote {md_path}")


@app.command("viz")
def viz_cmd(
    report_json: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="report.json from ksp-bench run",
    ),
    output: Path = typer.Option(
        Path("stack.html"),
        "--output",
        "-o",
        help="Self-contained HTML (stack flow + mean-time bars)",
    ),
    summary: bool = typer.Option(
        True,
        "--summary/--no-summary",
        help=(
            "Also write conclusions HTML next to --output "
            "(unless --summary-output is set)."
        ),
    ),
    summary_output: Path | None = typer.Option(
        None,
        "--summary-output",
        help="Path for conclusions HTML (default: <output-dir>/summary.html).",
    ),
    distributed: bool = typer.Option(
        True,
        "--distributed/--no-distributed",
        help=(
            "Also write S0/S1 footprint HTML next to --output "
            "(unless --distributed-output is set)."
        ),
    ),
    distributed_output: Path | None = typer.Option(
        None,
        "--distributed-output",
        help=(
            "Path for distributed footprint HTML "
            "(default: <output-dir>/distributed.html)."
        ),
    ),
) -> None:
    """Encode→wire→decode stack diagram plus bar chart of mean times per component."""

    from benchmark.viz.distributed_html import write_distributed_visualization
    from benchmark.viz.stack_html import write_stack_visualization
    from benchmark.viz.summary_html import write_summary_visualization

    sum_path: Path | None = None
    if summary:
        sum_path = summary_output or (output.parent / "summary.html")

    dist_path: Path | None = None
    if distributed:
        dist_path = distributed_output or (output.parent / "distributed.html")

    write_stack_visualization(
        report_json,
        output,
        companion_summary_path=sum_path,
        companion_distributed_path=dist_path,
    )
    typer.echo(f"Wrote {output}")
    if summary and sum_path is not None:
        write_summary_visualization(
            report_json,
            sum_path,
            companion_stack_path=output,
            companion_distributed_path=dist_path,
        )
        typer.echo(f"Wrote {sum_path}")
    if distributed and dist_path is not None:
        write_distributed_visualization(
            report_json,
            dist_path,
            companion_stack_path=output,
            companion_summary_path=sum_path,
        )
        typer.echo(f"Wrote {dist_path}")
