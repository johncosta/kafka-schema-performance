from __future__ import annotations

from typing import Any, cast

from benchmark.fixtures import event_pb2
from benchmark.models.event import AnalyticsEvent, EventContext


class ProtobufCodec:
    name = "protobuf"

    def encode(self, event: AnalyticsEvent) -> bytes:
        msg = _event_to_pb(event)
        return cast(bytes, msg.SerializeToString())

    def decode(self, data: bytes) -> AnalyticsEvent:
        msg = event_pb2.AnalyticsEvent()  # type: ignore[attr-defined]
        msg.ParseFromString(data)
        return _pb_to_event(msg)


def _event_to_pb(event: AnalyticsEvent) -> Any:
    msg = event_pb2.AnalyticsEvent()  # type: ignore[attr-defined]
    msg.event_id = event.event_id
    msg.ts_ms = event.ts_ms
    msg.user_id = event.user_id
    msg.props.update(event.props)
    if event.context is not None:
        msg.context.device_id = event.context.device_id
        msg.context.session_id = event.context.session_id
        msg.context.tags[:] = list(event.context.tags)
    if event.payload_blob:
        msg.payload_blob = event.payload_blob
    if event.new_field is not None:
        msg.new_field = event.new_field
    return msg


def _pb_to_event(msg: Any) -> AnalyticsEvent:
    c = msg.context
    if c.device_id or c.session_id or c.tags:
        context = EventContext(
            device_id=c.device_id,
            session_id=c.session_id,
            tags=tuple(c.tags),
        )
    else:
        context = None
    new_field = msg.new_field if msg.new_field else None
    return AnalyticsEvent(
        event_id=msg.event_id,
        ts_ms=msg.ts_ms,
        user_id=msg.user_id,
        props=dict(msg.props),
        context=context,
        payload_blob=bytes(msg.payload_blob),
        new_field=new_field,
    )
