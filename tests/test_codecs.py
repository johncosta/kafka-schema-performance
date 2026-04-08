from __future__ import annotations

from benchmark.codecs.avro_codec import AvroCodec, make_evolution_codec
from benchmark.codecs.json_codec import JsonCodec
from benchmark.codecs.protobuf_codec import ProtobufCodec
from benchmark.generate.records import PayloadProfile, golden_small_event, sample_event


def test_avro_roundtrip_golden() -> None:
    c = AvroCodec()
    e = golden_small_event()
    raw = c.encode(e)
    assert c.decode(raw) == e


def test_protobuf_roundtrip_golden() -> None:
    c = ProtobufCodec()
    e = golden_small_event()
    raw = c.encode(e)
    assert c.decode(raw) == e


def test_json_roundtrip_golden() -> None:
    c = JsonCodec()
    e = golden_small_event()
    raw = c.encode(e)
    assert c.decode(raw) == e


def test_avro_evolution_v1_to_v2() -> None:
    c = make_evolution_codec()
    e = sample_event(PayloadProfile.evolution, seed=7)
    raw = c.encode(e)
    out = c.decode(raw)
    assert out.new_field is None
    assert out.event_id == e.event_id


def test_all_formats_medium_roundtrip() -> None:
    e = sample_event(PayloadProfile.medium, seed=3)
    for codec in (AvroCodec(), ProtobufCodec(), JsonCodec()):
        assert codec.decode(codec.encode(e)) == e
