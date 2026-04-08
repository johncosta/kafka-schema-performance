from __future__ import annotations

import orjson

from benchmark.codecs.common import event_to_json_dict, json_dict_to_event
from benchmark.models.event import AnalyticsEvent

_JSON_OPTS = orjson.OPT_SORT_KEYS


class JsonCodec:
    name = "json"

    def encode(self, event: AnalyticsEvent) -> bytes:
        d = event_to_json_dict(event)
        return orjson.dumps(d, option=_JSON_OPTS)

    def decode(self, data: bytes) -> AnalyticsEvent:
        row = orjson.loads(data)
        assert isinstance(row, dict)
        return json_dict_to_event(row)
