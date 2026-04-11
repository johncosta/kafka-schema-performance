"""Session broker bootstrap: env ``KSP_KAFKA_BOOTSTRAP`` or Testcontainers."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest


def _bootstrap_from_env() -> str | None:
    v = os.environ.get("KSP_KAFKA_BOOTSTRAP", "").strip()
    return v or None


@pytest.fixture(scope="session")
def kafka_bootstrap_servers() -> Generator[str, None, None]:
    env = _bootstrap_from_env()
    if env:
        yield env
        return
    if os.environ.get("KSP_USE_TESTCONTAINERS", "").lower() not in ("1", "true", "yes"):
        pytest.skip(
            "Kafka E2E: set KSP_KAFKA_BOOTSTRAP=host:port (see "
            "docker/docker-compose.kafka.yml and make test-kafka), or "
            "KSP_USE_TESTCONTAINERS=1 with pip install -e '.[kafka]' and Docker",
        )
    try:
        from testcontainers.kafka import KafkaContainer
    except ImportError:
        pytest.skip("Kafka E2E: pip install -e '.[kafka]' for Testcontainers support")
    try:
        with KafkaContainer() as kafka:
            yield kafka.get_bootstrap_server()
    except Exception as exc:  # noqa: BLE001 — broker/Docker optional in default CI
        pytest.skip(f"Kafka broker not available ({exc})")
