"""Optional broker-backed checks (Kafka protocol).

Not part of default ``ksp-bench`` tiers.
"""

from benchmark.integration.kafka_e2e import (
    KAFKA_E2E_VERSION,
    attach_kafka_e2e_to_report,
    benchmark_kafka_case,
    build_kafka_e2e_block,
)

__all__ = [
    "KAFKA_E2E_VERSION",
    "attach_kafka_e2e_to_report",
    "benchmark_kafka_case",
    "build_kafka_e2e_block",
]
