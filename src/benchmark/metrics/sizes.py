from __future__ import annotations

from typing import Any


def confluent_value_envelope(
    *,
    payload_bytes: int,
    prefix_bytes: int = 5,
) -> dict[str, Any]:
    """Kafka/Confluent-style serialized value: prefix + payload (no record headers)."""

    return {
        "style": "confluent_wire_format_value",
        "prefix_bytes": prefix_bytes,
        "payload_bytes": payload_bytes,
        "total_value_bytes": payload_bytes + prefix_bytes,
        "notes": (
            "Default prefix: magic 0x00 (1 byte) + schema ID uint32 BE (4 bytes). "
            "Does not include Kafka record/batch headers or key bytes."
        ),
    }
