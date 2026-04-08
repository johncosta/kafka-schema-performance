from __future__ import annotations

import hashlib
from importlib import resources


def fixture_sha256() -> str:
    """Checksum over bundled schema and protobuf sources (deterministic order)."""

    h = hashlib.sha256()
    names = [
        "analytics_event.schema.json",
        "analytics_event_v1.avsc",
        "analytics_event_v2.avsc",
        "event.proto",
        "event_pb2.py",
    ]
    for name in names:
        data = resources.files("benchmark.fixtures").joinpath(name).read_bytes()
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
    return h.hexdigest()
