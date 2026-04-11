from __future__ import annotations

import orjson
import pytest
import zstandard
from google.protobuf.message import DecodeError

from benchmark.codecs.avro_codec import AvroCodec
from benchmark.codecs.json_codec import JsonCodec
from benchmark.codecs.protobuf_codec import ProtobufCodec
from benchmark.metrics.compress import decompress


def test_json_codec_decode_rejects_non_json() -> None:
    with pytest.raises(orjson.JSONDecodeError):
        JsonCodec().decode(b"not json {")


def test_json_codec_decode_rejects_invalid_utf8_string() -> None:
    with pytest.raises(orjson.JSONDecodeError):
        JsonCodec().decode(b'{"user_id": "\xff\xff"}')


def test_avro_codec_decode_rejects_truncated_wire() -> None:
    with pytest.raises(EOFError):
        AvroCodec().decode(b"\x00")


def test_avro_codec_decode_rejects_corrupt_wire() -> None:
    with pytest.raises(IndexError):
        AvroCodec().decode(b"\xff" * 32)


def test_protobuf_codec_decode_rejects_invalid_wire() -> None:
    with pytest.raises(DecodeError):
        ProtobufCodec().decode(b"\x0a\xff\x12\x02ab")


def test_zstd_decompress_rejects_garbage() -> None:
    with pytest.raises(zstandard.ZstdError):
        decompress("zstd", b"\x00not-a-zstd-frame")
