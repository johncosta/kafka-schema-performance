from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventContext:
    """Nested context for medium+ payload profiles."""

    device_id: str
    session_id: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class AnalyticsEvent:
    """Canonical domain record shared across Avro, Protobuf, and JSON codecs."""

    event_id: str
    ts_ms: int
    user_id: str
    props: dict[str, str]
    context: EventContext | None = None
    payload_blob: bytes = b""
    new_field: str | None = None
