from __future__ import annotations

import time
import tracemalloc
from typing import Any, Literal, cast

import yaml

from benchmark.codecs.avro_codec import AvroCodec, make_evolution_codec
from benchmark.codecs.base import Codec
from benchmark.codecs.json_codec import JsonCodec
from benchmark.codecs.protobuf_codec import ProtobufCodec
from benchmark.env import collect_environment
from benchmark.fixtures.checksum import fixture_sha256
from benchmark.generate.records import PayloadProfile, sample_event
from benchmark.metrics.compress import CompressionAlg, compress, decompress
from benchmark.metrics.stats import mb_per_second, summarize_times
from benchmark.models.event import AnalyticsEvent
from benchmark.report.render import render_markdown

ScenarioTier = Literal["S0", "S1"]

MEASUREMENT_MODEL: dict[str, Any] = {
    "timer": "time.perf_counter (wall time per iteration)",
    "threading_model": (
        "single-threaded sequential loop (CPython); no worker pool — "
        "CPU-bound codec work holds the GIL"
    ),
    "phases": {
        "encode": (
            "Wall time for serialize(domain→bytes). For S1, the timed "
            "window includes compression immediately after encode in the "
            "same iteration (see layer_cake)."
        ),
        "decode": (
            "Wall time for decompress-if-S1 then deserialize(bytes→domain). "
            "Schema validation is not separated; for Avro/protobuf/json it "
            "is part of the decode path."
        ),
        "round_trip": (
            "Single timer around encode (+ compress/decompress if S1) and "
            "decode in one pass; not the sum of separate encode/decode means."
        ),
    },
}


def _tracemalloc_round_trip_peak(
    codec: Codec,
    event: AnalyticsEvent,
    *,
    tier: ScenarioTier,
    compression: CompressionAlg,
) -> dict[str, Any]:
    """One post-warmup sample; tracemalloc is noisy — use for trends only."""

    tracemalloc.start()
    try:
        raw = codec.encode(event)
        if tier == "S1":
            raw = compress(compression, raw)
            raw = decompress(compression, raw)
        _ = codec.decode(raw)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "peak_bytes_traced": peak,
        "method": "tracemalloc",
        "caveat": (
            "Single sample after warmup; CPython allocator noise; not comparable "
            "across processes or platforms"
        ),
    }


def _select_codec(fmt: str, profile: PayloadProfile) -> Codec:
    if fmt == "avro":
        if profile is PayloadProfile.evolution:
            return make_evolution_codec()
        return AvroCodec()
    if fmt == "protobuf":
        return ProtobufCodec()
    if fmt == "json":
        return JsonCodec()
    raise ValueError(f"unknown format: {fmt!r}")


def bench_codec(
    codec: Codec,
    event: AnalyticsEvent,
    *,
    tier: ScenarioTier,
    compression: CompressionAlg,
    warmup: int,
    iterations: int,
    tracemalloc_sample: bool = False,
) -> dict[str, Any]:
    encoded_last: bytes | None = None
    for _ in range(warmup):
        raw = codec.encode(event)
        if tier == "S1":
            blob = compress(compression, raw)
            raw = decompress(compression, blob)
        _ = codec.decode(raw)
        encoded_last = codec.encode(event)

    if encoded_last is None:
        encoded_last = codec.encode(event)
    raw_wire = encoded_last
    compressed_wire = compress(compression, raw_wire) if tier == "S1" else raw_wire

    enc_times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        raw = codec.encode(event)
        if tier == "S1":
            _ = compress(compression, raw)
        enc_times.append(time.perf_counter() - t0)

    decode_blob = compress(compression, raw_wire) if tier == "S1" else raw_wire
    dec_times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        payload = decompress(compression, decode_blob) if tier == "S1" else decode_blob
        _ = codec.decode(payload)
        dec_times.append(time.perf_counter() - t0)

    rt_times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        raw = codec.encode(event)
        if tier == "S1":
            raw = compress(compression, raw)
            raw = decompress(compression, raw)
        _ = codec.decode(raw)
        rt_times.append(time.perf_counter() - t0)

    enc_stats = summarize_times(enc_times)
    dec_stats = summarize_times(dec_times)
    rt_stats = summarize_times(rt_times)
    raw_size = len(raw_wire)
    comp_size = len(compressed_wire) if tier == "S1" else raw_size

    allocations: dict[str, Any] | None = None
    if tracemalloc_sample:
        allocations = _tracemalloc_round_trip_peak(
            codec,
            event,
            tier=tier,
            compression=compression,
        )

    return {
        "codec": codec.name,
        "tier": tier,
        "compression": compression if tier == "S1" else "none",
        "raw_size_bytes": raw_size,
        "compressed_size_bytes": comp_size,
        "encode": enc_stats
        | {
            "encode_mb_per_s": mb_per_second(enc_stats["mean_s"], raw_size),
        },
        "decode": dec_stats
        | {
            "decode_mb_per_s": mb_per_second(dec_stats["mean_s"], raw_size),
        },
        "round_trip": rt_stats
        | {
            "round_trip_mb_per_s": mb_per_second(rt_stats["mean_s"], raw_size),
        },
        "layer_cake": _layer_cake(tier, compression),
        "allocations": allocations,
    }


def _layer_cake(tier: ScenarioTier, compression: CompressionAlg) -> dict[str, Any]:
    if tier == "S0":
        return {
            "included": ["codec encode/decode (in-process)", "same logical event"],
            "excluded": [
                "network",
                "Kafka client",
                "schema registry",
                "compression",
                "TLS",
            ],
        }
    return {
        "included": [
            "codec encode/decode",
            f"compression ({compression}) after encode",
            "decompress before decode",
        ],
        "excluded": ["network", "Kafka client", "schema registry", "TLS"],
    }


def load_rubric(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if data is None:
            return {}
        return cast(dict[str, Any], data)


def build_report(
    *,
    profiles: list[PayloadProfile],
    tier: ScenarioTier,
    formats: list[str],
    compression: CompressionAlg,
    warmup: int,
    iterations: int,
    seed: int,
    rubric_governance: str | None,
    rubric_maintainability: str | None,
    tracemalloc_sample: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        event = sample_event(profile, seed)
        for fmt in formats:
            codec = _select_codec(fmt, profile)
            row = bench_codec(
                codec,
                event,
                tier=tier,
                compression=compression,
                warmup=warmup,
                iterations=iterations,
                tracemalloc_sample=tracemalloc_sample,
            )
            row["payload_profile"] = profile.value
            rows.append(row)

    report: dict[str, Any] = {
        "report_version": 2,
        "scenario": {
            "payload_profiles": [p.value for p in profiles],
            "tier": tier,
            "formats": formats,
            "warmup_iterations": warmup,
            "timed_iterations": iterations,
            "seed": seed,
            "compression": compression,
        },
        "measurement": MEASUREMENT_MODEL,
        "environment": collect_environment(),
        "fixture_bundle_sha256": fixture_sha256(),
        "results": rows,
    }
    if rubric_governance:
        report["governance_rubric"] = load_rubric(rubric_governance)
    if rubric_maintainability:
        report["maintainability_rubric"] = load_rubric(rubric_maintainability)
    return report


def write_report_bundle(
    report: dict[str, Any],
    output_dir: str,
    *,
    write_markdown: bool = True,
) -> tuple[str, str | None]:
    import json
    import os

    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    md_path: str | None = None
    if write_markdown:
        md_path = os.path.join(output_dir, "report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_markdown(report))
    return json_path, md_path
