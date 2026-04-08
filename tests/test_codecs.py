from __future__ import annotations

from collections.abc import Callable

import pytest

from benchmark.codecs.avro_codec import AvroCodec, make_evolution_codec
from benchmark.codecs.json_codec import JsonCodec
from benchmark.codecs.protobuf_codec import ProtobufCodec
from benchmark.generate.records import (
    PayloadProfile,
    golden_evolution_event,
    golden_large_event,
    golden_medium_event,
    golden_small_event,
    sample_event,
)
from benchmark.models.event import AnalyticsEvent


@pytest.mark.parametrize(
    "golden",
    [
        golden_small_event,
        golden_medium_event,
        golden_large_event,
        golden_evolution_event,
    ],
)
def test_all_codecs_roundtrip_golden(golden: Callable[[], AnalyticsEvent]) -> None:
    e = golden()
    for codec in (AvroCodec(), ProtobufCodec(), JsonCodec()):
        assert codec.decode(codec.encode(e)) == e


def test_avro_evolution_v1_to_v2() -> None:
    c = make_evolution_codec()
    e = sample_event(PayloadProfile.evolution, seed=7)
    raw = c.encode(e)
    out = c.decode(raw)
    assert out.new_field is None
    assert out.event_id == e.event_id


def test_avro_evolution_codec_roundtrip_golden() -> None:
    c = make_evolution_codec()
    e = golden_evolution_event()
    raw = c.encode(e)
    assert c.decode(raw) == e


def test_all_formats_medium_roundtrip() -> None:
    e = sample_event(PayloadProfile.medium, seed=3)
    for codec in (AvroCodec(), ProtobufCodec(), JsonCodec()):
        assert codec.decode(codec.encode(e)) == e
