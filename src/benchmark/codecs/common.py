from __future__ import annotations

import base64
from typing import Any

from benchmark.models.event import AnalyticsEvent, EventContext


def event_to_avro_dict(
    event: AnalyticsEvent,
    *,
    writer_has_new_field: bool,
) -> dict[str, Any]:
    """Build an Avro payload dict. v1 writers omit ``new_field`` entirely."""
    ctx: Any
    if event.context is None:
        ctx = None
    else:
        ctx = {
            "device_id": event.context.device_id,
            "session_id": event.context.session_id,
            "tags": list(event.context.tags),
        }
    row: dict[str, Any] = {
        "event_id": event.event_id,
        "ts_ms": event.ts_ms,
        "user_id": event.user_id,
        "props": dict(event.props),
        "context": ctx,
        "payload_blob": event.payload_blob if event.payload_blob else None,
    }
    if writer_has_new_field:
        row["new_field"] = event.new_field
    return row


def avro_dict_to_event(row: dict[str, Any]) -> AnalyticsEvent:
    ctx_raw = row.get("context")
    context: EventContext | None
    if ctx_raw is None:
        context = None
    else:
        context = EventContext(
            device_id=str(ctx_raw["device_id"]),
            session_id=str(ctx_raw["session_id"]),
            tags=tuple(str(t) for t in ctx_raw["tags"]),
        )
    blob = row.get("payload_blob")
    payload_blob = b"" if blob is None else bytes(blob)
    nf = row.get("new_field")
    new_field = None if nf is None else str(nf)
    return AnalyticsEvent(
        event_id=str(row["event_id"]),
        ts_ms=int(row["ts_ms"]),
        user_id=str(row["user_id"]),
        props={str(k): str(v) for k, v in row["props"].items()},
        context=context,
        payload_blob=payload_blob,
        new_field=new_field,
    )


def event_to_json_dict(event: AnalyticsEvent) -> dict[str, Any]:
    """Canonical JSON-friendly dict: sorted keys at serialization time; base64 blob."""
    out: dict[str, Any] = {
        "event_id": event.event_id,
        "ts_ms": event.ts_ms,
        "user_id": event.user_id,
        "props": dict(event.props),
    }
    if event.context is not None:
        out["context"] = {
            "device_id": event.context.device_id,
            "session_id": event.context.session_id,
            "tags": list(event.context.tags),
        }
    else:
        out["context"] = None
    if event.payload_blob:
        out["payload_blob"] = base64.b64encode(event.payload_blob).decode("ascii")
    else:
        out["payload_blob"] = None
    out["new_field"] = event.new_field
    return out


def json_dict_to_event(row: dict[str, Any]) -> AnalyticsEvent:
    ctx_raw = row.get("context")
    context: EventContext | None
    if ctx_raw is None:
        context = None
    else:
        context = EventContext(
            device_id=str(ctx_raw["device_id"]),
            session_id=str(ctx_raw["session_id"]),
            tags=tuple(str(t) for t in ctx_raw["tags"]),
        )
    b64 = row.get("payload_blob")
    payload_blob = b""
    if isinstance(b64, str) and b64:
        payload_blob = base64.b64decode(b64.encode("ascii"))
    nf = row.get("new_field")
    new_field = None if nf is None else str(nf)
    return AnalyticsEvent(
        event_id=str(row["event_id"]),
        ts_ms=int(row["ts_ms"]),
        user_id=str(row["user_id"]),
        props={str(k): str(v) for k, v in dict(row["props"]).items()},
        context=context,
        payload_blob=payload_blob,
        new_field=new_field,
    )
