from __future__ import annotations

from typing import Any

LIMITATIONS: dict[str, Any] = {
    "summary": "Micro-benchmark caveats when interpreting this report.",
    "points": [
        "Wall-clock timings on a single process/OS; CPU frequency scaling, thermal "
        "throttling, and background load change run-to-run variance.",
        "CPython GIL: the default harness is single-threaded; numbers do not model "
        "multi-threaded producer pools or async pipelines.",
        "Low timed iteration counts increase statistical noise; raise --iterations "
        "before publishing headline figures.",
        "Compare tiers only across runs with matching scenario metadata "
        "(profiles, seed, formats, tier, compression, batch_size for S3/S4). "
        "S2 uses a loopback mock registry; S3/S4 use in-memory batches only—"
        "not real Kafka producer/consumer or broker latency.",
        "Codec deltas on synthetic payloads do not predict every production workload; "
        "treat small gaps as inconclusive without scenario alignment.",
    ],
    "interpretation_policy": (
        "Reports are scenario-labeled; avoid declaring a single universal winner "
        "from benchmark tables alone."
    ),
}


def limitations_for_report() -> dict[str, Any]:
    """Structured limitations block (Phase 8 / PRD limitations narrative)."""

    return dict(LIMITATIONS)
