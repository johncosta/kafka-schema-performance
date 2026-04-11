"""Kafka-protocol publish + consume timings (pre-serialized value bytes).

Uses ``kafka-python`` against any Kafka-compatible broker (e.g. Apache Kafka KRaft,
Testcontainers).
Metrics merge into ``report.json`` under ``kafka_e2e``.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

KAFKA_E2E_VERSION = 2

# Fixed API version: stable against Apache Kafka 3.8 (KRaft) and avoids
# kafka-python ``check_version`` / selector edge cases during broker startup.
_KAFKA_PYTHON_API_VERSION = (2, 8, 1)

# JSON-serializable defaults embedded in report.json for PRD traceability.
_KAFKA_E2E_PRODUCER_CONFIG: dict[str, Any] = {
    "acks": "all",
    "linger_ms": 0,
    "compression_type": None,
    "api_version": list(_KAFKA_PYTHON_API_VERSION),
}

_KAFKA_E2E_CONSUMER_CONFIG: dict[str, Any] = {
    "enable_auto_commit": False,
    "auto_offset_reset": "earliest",
    "consumer_timeout_ms": 120_000,
    "api_version": list(_KAFKA_PYTHON_API_VERSION),
}


def benchmark_kafka_case(
    *,
    bootstrap_servers: str,
    codec: str,
    payload_profile: str,
    serialize: Callable[[], bytes],
    warmup_messages: int,
    timed_messages: int,
    deserialize: Callable[[bytes], Any] | None = None,
) -> dict[str, Any]:
    """Publish then read back messages; timed produce window excludes warmup.

    When ``deserialize`` is set, an additional in-process loop times
    ``deserialize(value_bytes)`` using the same wire bytes as produce—this is
    **not** inside the Kafka consumer poll loop (see ``consume`` note).
    """

    from kafka import KafkaConsumer, KafkaProducer
    from kafka.admin import KafkaAdminClient, NewTopic

    topic = f"ksp-e2e-{uuid.uuid4().hex[:16]}"
    admin = KafkaAdminClient(
        bootstrap_servers=bootstrap_servers,
        client_id="ksp-admin",
        api_version=_KAFKA_PYTHON_API_VERSION,
    )
    try:
        admin.create_topics(
            [
                NewTopic(
                    name=topic,
                    num_partitions=1,
                    replication_factor=1,
                ),
            ],
            validate_only=False,
        )
    except Exception:
        admin.close()
        raise

    got = 0
    ser_n = max(20, warmup_messages)
    t_s0 = time.perf_counter()
    for _ in range(ser_n):
        _ = serialize()
    t_s1 = time.perf_counter()
    serialize_mean_s = (t_s1 - t_s0) / ser_n

    value = serialize()
    value_len = len(value)

    deserialize_block: dict[str, Any] | None = None
    if deserialize is not None:
        dec_n = max(20, warmup_messages)
        t_d0 = time.perf_counter()
        for _ in range(dec_n):
            _ = deserialize(value)
        t_d1 = time.perf_counter()
        deserialize_mean_s = (t_d1 - t_d0) / dec_n
        deserialize_block = {
            "iterations": dec_n,
            "mean_s": deserialize_mean_s,
            "note": (
                "In-process decode of the same value bytes used for produce; excludes "
                "Kafka consumer poll/fetch and per-record decode inside poll."
            ),
        }

    try:
        producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            client_id="ksp-producer",
            api_version=_KAFKA_PYTHON_API_VERSION,
            acks=_KAFKA_E2E_PRODUCER_CONFIG["acks"],
            linger_ms=_KAFKA_E2E_PRODUCER_CONFIG["linger_ms"],
            compression_type=_KAFKA_E2E_PRODUCER_CONFIG["compression_type"],
        )
        try:
            for _ in range(warmup_messages):
                producer.send(topic, value=value).get(timeout=30)
            producer.flush()

            t_p0 = time.perf_counter()
            for _ in range(timed_messages):
                producer.send(topic, value=value).get(timeout=30)
            producer.flush()
            t_p1 = time.perf_counter()
            produce_wall_s = t_p1 - t_p0
        finally:
            producer.close()

        consume_wall_s = float("nan")
        group_id = f"ksp-{uuid.uuid4().hex[:12]}"
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            client_id="ksp-consumer",
            api_version=_KAFKA_PYTHON_API_VERSION,
            enable_auto_commit=_KAFKA_E2E_CONSUMER_CONFIG["enable_auto_commit"],
            auto_offset_reset=_KAFKA_E2E_CONSUMER_CONFIG["auto_offset_reset"],
            consumer_timeout_ms=_KAFKA_E2E_CONSUMER_CONFIG["consumer_timeout_ms"],
        )
        total = warmup_messages + timed_messages
        try:
            while not consumer.assignment():
                consumer.poll(timeout_ms=1000)
            consumer.seek_to_beginning()

            t_c0 = time.perf_counter()
            while got < total:
                batches = consumer.poll(timeout_ms=5000)
                if not batches:
                    break
                for _tp, records in batches.items():
                    got += len(records)
            t_c1 = time.perf_counter()
            consume_wall_s = t_c1 - t_c0
            if got != total:
                raise RuntimeError(
                    f"kafka consume incomplete: expected {total} messages, got {got}",
                )
        finally:
            consumer.close()
    finally:
        try:
            admin.delete_topics([topic])
        except Exception:
            pass
        admin.close()

    pm = float(timed_messages)
    tot_f = float(total)
    produce_msgs_s = (pm / produce_wall_s) if produce_wall_s > 0 else float("nan")
    produce_mb_s = (
        ((value_len * pm) / produce_wall_s) / (1024.0 * 1024.0)
        if produce_wall_s > 0
        else float("nan")
    )
    consume_msgs_s = (
        (tot_f / consume_wall_s)
        if consume_wall_s == consume_wall_s and consume_wall_s > 0
        else float("nan")
    )
    consume_mb_s = (
        ((value_len * tot_f) / consume_wall_s) / (1024.0 * 1024.0)
        if consume_wall_s == consume_wall_s and consume_wall_s > 0
        else float("nan")
    )
    return {
        "codec": codec,
        "payload_profile": payload_profile,
        "value_bytes": value_len,
        "warmup_messages": warmup_messages,
        "timed_messages": timed_messages,
        "serialize": {
            "iterations": ser_n,
            "mean_s": serialize_mean_s,
            "note": "In-process codec.encode before broker send",
        },
        **({"deserialize": deserialize_block} if deserialize_block else {}),
        "produce": {
            "messages": timed_messages,
            "wall_s": produce_wall_s,
            "mean_per_message_s": produce_wall_s / pm if pm else float("nan"),
            "throughput_messages_per_s": produce_msgs_s,
            "throughput_megabytes_per_s": produce_mb_s,
        },
        "consume": {
            "messages_read": total,
            "wall_s": consume_wall_s,
            "mean_per_message_s": (
                consume_wall_s / float(total) if total else float("nan")
            ),
            "throughput_messages_per_s": consume_msgs_s,
            "throughput_megabytes_per_s": consume_mb_s,
            "note": (
                "Fresh consumer group; read from partition start until all "
                "warmup+timed records received"
            ),
        },
    }


def build_kafka_e2e_block(
    *,
    bootstrap_servers: str,
    broker_implementation: str,
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Top-level ``kafka_e2e`` object for ``report.json``."""

    return {
        "kafka_e2e_version": KAFKA_E2E_VERSION,
        "broker_implementation": broker_implementation,
        "bootstrap_servers": bootstrap_servers,
        "client": {
            "library": "kafka-python",
            "api_version": list(_KAFKA_PYTHON_API_VERSION),
        },
        "producer_config": dict(_KAFKA_E2E_PRODUCER_CONFIG),
        "consumer_config": dict(_KAFKA_E2E_CONSUMER_CONFIG),
        "phases": {
            "serialize": (
                "In-process serialize(domain→bytes) mean over several iterations "
                "before broker I/O."
            ),
            "produce": (
                "Synchronous Kafka produce (acks=all) for pre-serialized value bytes; "
                "timed window excludes warmup sends."
            ),
            "consume": (
                "Fresh consumer group, read all warmup+timed records from partition "
                "start; wall time covers polling until last record (decode of value "
                "bytes not isolated from fetch loop)."
            ),
            "deserialize": (
                "Optional per-case block: in-process decode mean on the same value "
                "bytes as produce, measured outside the consumer (see case.deserialize "
                "when the benchmark passes a decode callback)."
            ),
        },
        "roadmap": (
            "Optional extensions (PRD §6.3.1): producer compression, linger/batch "
            "tuning, acks variants, keys/headers, partitioned topics, async flush "
            "throughput, per-record decode inside consumer poll."
        ),
        "cases": cases,
    }


def attach_kafka_e2e_to_report(
    report: dict[str, Any],
    kafka_block: dict[str, Any],
) -> None:
    """Mutates ``report`` in place: sets ``kafka_e2e`` and ``scenario.integrations``."""

    report["kafka_e2e"] = kafka_block
    scen = report.get("scenario")
    if isinstance(scen, dict):
        ints = scen.get("integrations")
        if isinstance(ints, list):
            if "kafka_e2e" not in ints:
                ints.append("kafka_e2e")
        else:
            scen["integrations"] = ["kafka_e2e"]
