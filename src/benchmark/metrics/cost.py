from __future__ import annotations

from typing import Any


def derived_cost_model(
    mean_wire_bytes: float,
    *,
    sensitivity_pct: float = 20.0,
) -> dict[str, Any]:
    """PRD section 6.2 reference formulas + ±payload sensitivity (illustrative)."""

    if mean_wire_bytes != mean_wire_bytes:  # NaN
        span_low = float("nan")
        span_high = float("nan")
    else:
        f = sensitivity_pct / 100.0
        span_low = mean_wire_bytes * (1.0 - f)
        span_high = mean_wire_bytes * (1.0 + f)

    return {
        "reference_formulas": {
            "egress_GB_month": (
                "records_per_month * mean_wire_bytes * replication_factor "
                "* fan_out_factor / 1e9"
            ),
            "retention_bytes": (
                "records_per_day * mean_disk_bytes * retention_days "
                "* replication_factor"
            ),
        },
        "sensitivity_payload_plus_minus_pct": sensitivity_pct,
        "illustrative_mean_wire_bytes_span": {
            "low": span_low,
            "high": span_high,
        },
        "notes": (
            "Plug measured mean_wire_bytes (raw encoded) or compressed sizes for "
            "mean_disk_bytes where appropriate. Not billing data."
        ),
    }
