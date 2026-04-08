from __future__ import annotations

import json
from importlib import resources
from io import BytesIO
from typing import Any, cast

import fastavro

from benchmark.codecs.common import avro_dict_to_event, event_to_avro_dict
from benchmark.models.event import AnalyticsEvent


def _load_schema_dict(name: str) -> dict[str, Any]:
    path = resources.files("benchmark.fixtures").joinpath(name)
    raw = path.read_text(encoding="utf-8")
    return cast(dict[str, Any], json.loads(raw))


class AvroCodec:
    name = "avro"

    def __init__(
        self,
        *,
        writer_schema_name: str = "analytics_event_v2.avsc",
        reader_schema_name: str = "analytics_event_v2.avsc",
    ) -> None:
        self._writer_schema = _load_schema_dict(writer_schema_name)
        self._reader_schema = _load_schema_dict(reader_schema_name)
        fields = {str(f["name"]) for f in self._writer_schema["fields"]}
        self._writer_has_new_field = "new_field" in fields

    def encode(self, event: AnalyticsEvent) -> bytes:
        buf = BytesIO()
        payload = event_to_avro_dict(
            event,
            writer_has_new_field=self._writer_has_new_field,
        )
        fastavro.schemaless_writer(buf, self._writer_schema, payload)
        return buf.getvalue()

    def decode(self, data: bytes) -> AnalyticsEvent:
        buf = BytesIO(data)
        row = fastavro.schemaless_reader(
            buf,
            self._writer_schema,
            reader_schema=self._reader_schema,
        )
        return avro_dict_to_event(cast(dict[str, Any], row))


def make_evolution_codec() -> AvroCodec:
    """Writer v1 (no ``new_field``) → reader v2."""

    return AvroCodec(
        writer_schema_name="analytics_event_v1.avsc",
        reader_schema_name="analytics_event_v2.avsc",
    )
