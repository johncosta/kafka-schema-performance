from __future__ import annotations

import gzip
from typing import Literal

import zstandard

CompressionAlg = Literal["none", "gzip", "zstd"]

DEFAULT_GZIP_COMPRESSLEVEL = 6
DEFAULT_ZSTD_LEVEL = 3


def compress(
    algorithm: CompressionAlg,
    data: bytes,
    *,
    level: int | None = None,
) -> bytes:
    if algorithm == "none":
        return data
    if algorithm == "gzip":
        lvl = DEFAULT_GZIP_COMPRESSLEVEL if level is None else level
        return gzip.compress(data, compresslevel=lvl)
    if algorithm == "zstd":
        lvl = DEFAULT_ZSTD_LEVEL if level is None else level
        cctx = zstandard.ZstdCompressor(level=lvl)
        return cctx.compress(data)
    raise ValueError(f"unknown compression: {algorithm!r}")


def decompress(algorithm: CompressionAlg, data: bytes) -> bytes:
    if algorithm == "none":
        return data
    if algorithm == "gzip":
        return gzip.decompress(data)
    if algorithm == "zstd":
        dctx = zstandard.ZstdDecompressor()
        return dctx.decompress(data)
    raise ValueError(f"unknown compression: {algorithm!r}")
