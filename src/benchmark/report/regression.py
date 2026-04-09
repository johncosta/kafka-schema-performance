from __future__ import annotations

import json
from typing import Any


def _scenario_fingerprint(scenario: dict[str, Any]) -> tuple[Any, ...]:
    return (
        scenario.get("tier"),
        scenario.get("seed"),
        tuple(scenario.get("payload_profiles", [])),
        tuple(scenario.get("formats", [])),
        scenario.get("compression"),
        scenario.get("timed_iterations"),
        scenario.get("batch_size"),
    )


def _rows_by_key(results: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for row in results:
        prof = str(row.get("payload_profile", ""))
        codec = str(row.get("codec", ""))
        rt = row.get("round_trip")
        if isinstance(rt, dict) and "mean_s" in rt:
            mean = float(rt["mean_s"])
            if mean == mean:  # not NaN
                out[(prof, codec)] = mean
    return out


def regression_check_against_baseline_file(
    current_report: dict[str, Any],
    baseline_path: str,
    *,
    warn_ratio: float,
) -> dict[str, Any]:
    """
    Optional Phase-8 regression hints: warn if round_trip.mean_s worsens vs baseline.

    Baseline must match tier, seed, payload_profiles, formats, compression,
    timed_iterations, and batch_size (S3/S4) so comparisons are apples-to-apples.
    """

    try:
        with open(baseline_path, encoding="utf-8") as f:
            baseline = json.load(f)
    except OSError as e:
        return {
            "skipped": True,
            "reason": f"could not read baseline: {e}",
            "baseline_path": baseline_path,
        }
    except json.JSONDecodeError as e:
        return {
            "skipped": True,
            "reason": f"invalid JSON in baseline: {e}",
            "baseline_path": baseline_path,
        }

    cur_scen = current_report.get("scenario")
    base_scen = baseline.get("scenario")
    if not isinstance(cur_scen, dict) or not isinstance(base_scen, dict):
        return {
            "skipped": True,
            "reason": "missing scenario block",
            "baseline_path": baseline_path,
        }

    if _scenario_fingerprint(cur_scen) != _scenario_fingerprint(base_scen):
        return {
            "skipped": True,
            "reason": (
                "scenario fingerprint mismatch (tier, seed, profiles, formats, "
                "compression, timed_iterations, or batch_size differ)"
            ),
            "baseline_path": baseline_path,
            "current_fingerprint": _scenario_fingerprint(cur_scen),
            "baseline_fingerprint": _scenario_fingerprint(base_scen),
        }

    base_results = baseline.get("results")
    cur_results = current_report.get("results")
    if not isinstance(base_results, list) or not isinstance(cur_results, list):
        return {
            "skipped": True,
            "reason": "missing results arrays",
            "baseline_path": baseline_path,
        }

    base_map = _rows_by_key(base_results)
    warnings: list[dict[str, Any]] = []
    for row in cur_results:
        prof = str(row.get("payload_profile", ""))
        codec = str(row.get("codec", ""))
        key = (prof, codec)
        if key not in base_map:
            continue
        rt = row.get("round_trip")
        if not isinstance(rt, dict) or "mean_s" not in rt:
            continue
        cur_mean = float(rt["mean_s"])
        if cur_mean != cur_mean:
            continue
        base_mean = base_map[key]
        if base_mean <= 0:
            continue
        threshold = base_mean * (1.0 + warn_ratio)
        if cur_mean > threshold:
            warnings.append(
                {
                    "payload_profile": prof,
                    "codec": codec,
                    "baseline_round_trip_mean_s": base_mean,
                    "current_round_trip_mean_s": cur_mean,
                    "warn_ratio": warn_ratio,
                    "message": (
                        f"round-trip mean {cur_mean:.6e}s exceeds baseline "
                        f"{base_mean:.6e}s by more than {warn_ratio:.0%}"
                    ),
                }
            )

    return {
        "skipped": False,
        "baseline_path": baseline_path,
        "warn_ratio": warn_ratio,
        "warnings": warnings,
        "note": (
            "Heuristic only; micro-benchmark noise often dominates. "
            "Treat as a prompt to re-run, not a failure gate."
        ),
    }
