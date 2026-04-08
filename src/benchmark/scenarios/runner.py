from __future__ import annotations

import time
import tracemalloc
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from benchmark.codecs.avro_codec import AvroCodec, make_evolution_codec
from benchmark.codecs.base import Codec
from benchmark.codecs.json_codec import JsonCodec
from benchmark.codecs.protobuf_codec import ProtobufCodec
from benchmark.env import collect_environment, collect_pip_freeze_integrity
from benchmark.fixtures.checksum import fixture_sha256
from benchmark.generate.records import PayloadProfile, sample_event
from benchmark.metrics.compress import (
    DEFAULT_GZIP_COMPRESSLEVEL,
    DEFAULT_ZSTD_LEVEL,
    CompressionAlg,
    compress,
    decompress,
)
from benchmark.metrics.cost import derived_cost_model
from benchmark.metrics.sizes import confluent_value_envelope
from benchmark.metrics.stats import (
    mb_per_second,
    summarize_byte_lengths,
    summarize_times,
)
from benchmark.models.event import AnalyticsEvent
from benchmark.report.limitations import limitations_for_report
from benchmark.report.regression import regression_check_against_baseline_file
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
    "tier_s1_vs_s0": (
        "S1 includes compressor CPU in the same timed windows as the codec. "
        "S0 is codec-only. Compare by re-running the same scenario/seed/formats "
        "with --tier S0 and --tier S1; do not compare S1 rows to S0 from different "
        "reports without matching scenario metadata."
    ),
}


def _compress_s1_wire(
    algorithm: CompressionAlg,
    payload: bytes,
    *,
    s1_gzip_level: int | None,
    s1_zstd_level: int | None,
) -> bytes:
    """Compress raw encoded bytes using the tier-S1 algorithm and levels."""

    if algorithm == "none":
        return payload
    if algorithm == "gzip":
        return compress("gzip", payload, level=s1_gzip_level)
    return compress("zstd", payload, level=s1_zstd_level)


def _tracemalloc_round_trip_peak(
    codec: Codec,
    event: AnalyticsEvent,
    *,
    tier: ScenarioTier,
    compression: CompressionAlg,
    s1_gzip_level: int | None,
    s1_zstd_level: int | None,
) -> dict[str, Any]:
    """One post-warmup sample; tracemalloc is noisy — use for trends only."""

    tracemalloc.start()
    try:
        raw = codec.encode(event)
        if tier == "S1":
            raw = _compress_s1_wire(
                compression,
                raw,
                s1_gzip_level=s1_gzip_level,
                s1_zstd_level=s1_zstd_level,
            )
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
    gzip_level: int = 6,
    zstd_level: int = 3,
    include_confluent_envelope: bool = False,
    confluent_prefix_bytes: int = 5,
    s1_gzip_level: int | None = None,
    s1_zstd_level: int | None = None,
) -> dict[str, Any]:
    encoded_last: bytes | None = None
    for _ in range(warmup):
        raw = codec.encode(event)
        if tier == "S1":
            blob = _compress_s1_wire(
                compression,
                raw,
                s1_gzip_level=s1_gzip_level,
                s1_zstd_level=s1_zstd_level,
            )
            raw = decompress(compression, blob)
        _ = codec.decode(raw)
        encoded_last = codec.encode(event)

    if encoded_last is None:
        encoded_last = codec.encode(event)
    raw_wire = encoded_last
    compressed_wire = (
        _compress_s1_wire(
            compression,
            raw_wire,
            s1_gzip_level=s1_gzip_level,
            s1_zstd_level=s1_zstd_level,
        )
        if tier == "S1"
        else raw_wire
    )

    enc_times: list[float] = []
    wire_len_samples: list[int] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        raw = codec.encode(event)
        wire_len_samples.append(len(raw))
        if tier == "S1":
            _ = _compress_s1_wire(
                compression,
                raw,
                s1_gzip_level=s1_gzip_level,
                s1_zstd_level=s1_zstd_level,
            )
        enc_times.append(time.perf_counter() - t0)

    decode_blob = (
        _compress_s1_wire(
            compression,
            raw_wire,
            s1_gzip_level=s1_gzip_level,
            s1_zstd_level=s1_zstd_level,
        )
        if tier == "S1"
        else raw_wire
    )
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
            raw = _compress_s1_wire(
                compression,
                raw,
                s1_gzip_level=s1_gzip_level,
                s1_zstd_level=s1_zstd_level,
            )
            raw = decompress(compression, raw)
        _ = codec.decode(raw)
        rt_times.append(time.perf_counter() - t0)

    enc_stats = summarize_times(enc_times)
    dec_stats = summarize_times(dec_times)
    rt_stats = summarize_times(rt_times)
    raw_size = len(raw_wire)
    comp_size = len(compressed_wire) if tier == "S1" else raw_size

    gzip_level_used = (
        s1_gzip_level if s1_gzip_level is not None else DEFAULT_GZIP_COMPRESSLEVEL
    )
    zstd_level_used = s1_zstd_level if s1_zstd_level is not None else DEFAULT_ZSTD_LEVEL
    s1_timed_compression: dict[str, Any] | None = None
    if tier == "S1":
        s1_timed_compression = {
            "timed_algorithm": compression,
            "gzip_level_used": gzip_level_used if compression == "gzip" else None,
            "zstd_level_used": zstd_level_used if compression == "zstd" else None,
            "raw_bytes": raw_size,
            "compressed_bytes": comp_size,
            "ratio_compressed_to_raw": (
                (comp_size / raw_size) if raw_size else float("nan")
            ),
            "note": (
                "Separate from Phase-3 gzip/zstd probes on raw wire "
                "(scenario size_and_cost levels)."
            ),
        }

    raw_len_stats = summarize_byte_lengths(wire_len_samples)
    gzip_blob = compress("gzip", raw_wire, level=gzip_level)
    zstd_blob = compress("zstd", raw_wire, level=zstd_level)
    mean_raw = float(raw_len_stats["mean"])

    def _ratio_to_raw(compressed_len: int) -> float:
        if mean_raw <= 0:
            return float("nan")
        return compressed_len / mean_raw

    compressed_payload = {
        "gzip": {
            "compresslevel": gzip_level,
            "bytes": len(gzip_blob),
            "ratio_to_raw_mean": _ratio_to_raw(len(gzip_blob)),
        },
        "zstd": {
            "level": zstd_level,
            "bytes": len(zstd_blob),
            "ratio_to_raw_mean": _ratio_to_raw(len(zstd_blob)),
        },
    }
    kafka_shaped: dict[str, Any] | None = None
    if include_confluent_envelope:
        kafka_shaped = confluent_value_envelope(
            payload_bytes=raw_size,
            prefix_bytes=confluent_prefix_bytes,
        )
    derived_cost = derived_cost_model(mean_raw)

    allocations: dict[str, Any] | None = None
    if tracemalloc_sample:
        allocations = _tracemalloc_round_trip_peak(
            codec,
            event,
            tier=tier,
            compression=compression,
            s1_gzip_level=s1_gzip_level,
            s1_zstd_level=s1_zstd_level,
        )

    enc_block: dict[str, Any] = enc_stats | {
        "encode_mb_per_s": mb_per_second(enc_stats["mean_s"], raw_size),
    }
    dec_block: dict[str, Any] = dec_stats | {
        "decode_mb_per_s": mb_per_second(dec_stats["mean_s"], raw_size),
    }
    rt_block: dict[str, Any] = rt_stats | {
        "round_trip_mb_per_s": mb_per_second(rt_stats["mean_s"], raw_size),
    }
    if tier == "S1":
        enc_block["encode_compressed_wire_mb_per_s"] = mb_per_second(
            enc_stats["mean_s"],
            comp_size,
        )
        dec_block["decode_compressed_input_mb_per_s"] = mb_per_second(
            dec_stats["mean_s"],
            comp_size,
        )
        rt_block["round_trip_compressed_wire_mb_per_s"] = mb_per_second(
            rt_stats["mean_s"],
            comp_size,
        )

    out: dict[str, Any] = {
        "codec": codec.name,
        "tier": tier,
        "compression": compression if tier == "S1" else "none",
        "raw_size_bytes": raw_size,
        "compressed_size_bytes": comp_size,
        "encode": enc_block,
        "decode": dec_block,
        "round_trip": rt_block,
        "raw_encoded_bytes": raw_len_stats,
        "compressed_payload_bytes": compressed_payload,
        "kafka_shaped": kafka_shaped,
        "derived_cost": derived_cost,
        "layer_cake": _layer_cake(tier, compression),
        "allocations": allocations,
    }
    if s1_timed_compression is not None:
        out["s1_timed_compression"] = s1_timed_compression
    return out


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
            f"compression ({compression}) after encode (CPU in encode timing)",
            "decompress before decode (CPU in decode timing)",
            "round-trip timer includes compress+decompress between codec phases",
        ],
        "excluded": ["network", "Kafka client", "schema registry", "TLS"],
    }


def load_rubric(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
        if data is None:
            return {}
        return cast(dict[str, Any], data)


def embed_rubric(path: str) -> dict[str, Any]:
    """Load YAML and pin ``rubric_ref`` + ``source_file`` for report JSON / appendix."""

    p = Path(path)
    raw = load_rubric(path)
    ref = str(raw.get("rubric_id") or p.stem)
    merged: dict[str, Any] = {"source_file": p.name}
    merged.update(raw)
    merged["rubric_ref"] = ref
    return merged


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
    gzip_level: int = 6,
    zstd_level: int = 3,
    include_confluent_envelope: bool = False,
    confluent_prefix_bytes: int = 5,
    s1_gzip_level: int | None = None,
    s1_zstd_level: int | None = None,
    baseline_report_path: str | None = None,
    regression_warn_ratio: float = 0.2,
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
                gzip_level=gzip_level,
                zstd_level=zstd_level,
                include_confluent_envelope=include_confluent_envelope,
                confluent_prefix_bytes=confluent_prefix_bytes,
                s1_gzip_level=s1_gzip_level,
                s1_zstd_level=s1_zstd_level,
            )
            row["payload_profile"] = profile.value
            rows.append(row)

    rubric_index: list[str] = []

    scenario_block: dict[str, Any] = {
        "payload_profiles": [p.value for p in profiles],
        "tier": tier,
        "formats": formats,
        "warmup_iterations": warmup,
        "timed_iterations": iterations,
        "seed": seed,
        "compression": compression,
        "size_and_cost": {
            "gzip_compresslevel": gzip_level,
            "zstd_level": zstd_level,
            "include_confluent_envelope": include_confluent_envelope,
            "confluent_prefix_bytes": (
                confluent_prefix_bytes if include_confluent_envelope else None
            ),
        },
    }
    if tier == "S1":
        scenario_block["s1"] = {
            "timed_compression_algorithm": compression,
            "gzip_level_cli": s1_gzip_level,
            "zstd_level_cli": s1_zstd_level,
            "default_gzip_level": DEFAULT_GZIP_COMPRESSLEVEL,
            "default_zstd_level": DEFAULT_ZSTD_LEVEL,
            "note": (
                "Null CLI level means default above. Timed loop uses that level; "
                "size_and_cost gzip/zstd are separate probes on raw wire."
            ),
        }

    report: dict[str, Any] = {
        "report_version": 6,
        "scenario": scenario_block,
        "measurement": MEASUREMENT_MODEL,
        "environment": collect_environment(),
        "fixture_bundle_sha256": fixture_sha256(),
        "limitations": limitations_for_report(),
        "artifact_integrity": collect_pip_freeze_integrity(),
        "results": rows,
    }
    if rubric_governance:
        gov = embed_rubric(rubric_governance)
        report["governance_rubric"] = gov
        rubric_index.append(str(gov["rubric_ref"]))
    if rubric_maintainability:
        maint = embed_rubric(rubric_maintainability)
        report["maintainability_rubric"] = maint
        rubric_index.append(str(maint["rubric_ref"]))
    if rubric_index:
        report["rubric_index"] = rubric_index
    if baseline_report_path:
        report["regression_check"] = regression_check_against_baseline_file(
            report,
            baseline_report_path,
            warn_ratio=regression_warn_ratio,
        )
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
