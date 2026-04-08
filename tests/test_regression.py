from __future__ import annotations

import json
from pathlib import Path

from benchmark.report.regression import regression_check_against_baseline_file


def _scenario() -> dict[str, object]:
    return {
        "tier": "S0",
        "seed": 1,
        "payload_profiles": ["small"],
        "formats": ["json"],
        "compression": "zstd",
        "timed_iterations": 10,
    }


def _report(mean_s: float) -> dict[str, object]:
    return {
        "scenario": _scenario(),
        "results": [
            {
                "payload_profile": "small",
                "codec": "json",
                "round_trip": {"mean_s": mean_s},
            },
        ],
    }


def test_regression_warns_when_round_trip_exceeds_threshold(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(_report(1e-6)), encoding="utf-8")
    current = _report(2e-6)
    rc = regression_check_against_baseline_file(
        current,
        str(baseline_path),
        warn_ratio=0.2,
    )
    assert rc["skipped"] is False
    assert len(rc["warnings"]) == 1
    w0 = rc["warnings"][0]
    assert w0["payload_profile"] == "small"
    assert "exceeds baseline" in w0["message"]


def test_regression_skips_on_fingerprint_mismatch(tmp_path: Path) -> None:
    base = _report(1e-6)
    base["scenario"] = {**_scenario(), "seed": 99}
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(base), encoding="utf-8")
    rc = regression_check_against_baseline_file(
        _report(9e-6),
        str(baseline_path),
        warn_ratio=0.2,
    )
    assert rc["skipped"] is True
    assert "fingerprint" in str(rc["reason"])
