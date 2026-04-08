from __future__ import annotations

from pathlib import Path

import typer

from benchmark.generate.records import PayloadProfile
from benchmark.scenarios.runner import (
    ScenarioTier,
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
        help="S Codec in-process; S1 codec + compression",
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
) -> None:
    """Run benchmark matrix and write report.json (+ report.md)."""

    profiles = _parse_scenarios(scenario)
    if tier not in ("S0", "S1"):
        raise typer.BadParameter("tier must be S0 or S1")
    tier_t: ScenarioTier = tier  # type: ignore[assignment]
    fmt_list = _parse_formats(formats)
    if tier == "S0" and compression != "zstd":
        # allow but note compression unused for S0
        pass
    comp: str = compression
    if comp not in ("gzip", "zstd"):
        raise typer.BadParameter(
            "compression must be gzip or zstd for S1; ignored for S0",
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
    )
    json_path, md_path = write_report_bundle(report, str(output_dir))
    typer.echo(f"Wrote {json_path}")
    if md_path:
        typer.echo(f"Wrote {md_path}")
