from __future__ import annotations

from typing import Protocol

from benchmark.models.event import AnalyticsEvent


class Codec(Protocol):
    """Format-specific serializer/deserializer for `AnalyticsEvent`."""

    name: str

    def encode(self, event: AnalyticsEvent) -> bytes: ...

    def decode(self, data: bytes) -> AnalyticsEvent: ...
