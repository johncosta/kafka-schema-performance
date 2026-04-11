from __future__ import annotations

from typing import Any

LIMITATIONS: dict[str, Any] = {
    "summary": "Micro-benchmark caveats when interpreting this report.",
    "evidence_coverage": {
        "summary": (
            "PRD §6.6 scope: metrics below are intentionally labeled as not produced "
            "by this harness so reports are not read as covering them."
        ),
        "not_measured": [
            "Consumer lag, broker replication, and cross-region latency.",
            "TLS, SASL, or HTTP authentication on schema registry or Kafka clients.",
            "Multi-broker clusters, partitions, or idempotent producer settings.",
            "Decode success rates or latency under adversarial or corrupted payloads.",
            "Strict statistical confidence intervals or cross-machine reproducibility.",
            (
                "Throughput under sustained parallel producer workers "
                "(see threading model)."
            ),
        ],
        "test_and_ci": (
            "Deterministic pytest (excluding @pytest.mark.kafka) and optional "
            "Kafka E2E when KSP_KAFKA_BOOTSTRAP is set; see Makefile targets "
            "`test-ci` vs `test`."
        ),
    },
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
