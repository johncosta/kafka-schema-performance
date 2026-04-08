from __future__ import annotations

from benchmark.codecs.json_codec import JsonCodec
from benchmark.generate.records import golden_small_event
from benchmark.scenarios.runner import bench_codec


def test_bench_codec_smoke_s0() -> None:
    r = bench_codec(
        JsonCodec(),
        golden_small_event(),
        tier="S0",
        compression="zstd",
        warmup=2,
        iterations=10,
    )
    assert r["codec"] == "json"
    assert r["raw_size_bytes"] > 0
    assert r["raw_size_bytes"] == r["compressed_size_bytes"]
