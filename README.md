# kafka-schema-performance

Benchmark harness comparing **Apache Avro**, **Protocol Buffers**, and **JSON** (UTF-8 via **orjson**, sorted keys) on shared synthetic payloads. See the [PRD](docs/PRD-benchmark-utility.md) for goals and metrics, and the [implementation plan](docs/IMPLEMENTATION-PLAN.md) for phased delivery.

## Requirements

- Python **3.11** or **3.12**

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run benchmarks

```bash
ksp-bench run --scenario small --tier S0 --formats all --output-dir reports/
# PRD-style matrix in one report: 3 payload profiles × all formats (S0)
ksp-bench run --scenario all --tier S0 --formats all --output-dir reports/
```

- **Profiles:** `small`, `medium`, `large`, `evolution`, **`all`** (runs small+medium+large), or a **comma-separated** list (e.g. `small,medium`). Evolution uses Avro schema v1 → v2 when format is Avro.
- **Tiers:** `S0` codec only; `S1` times **encode→compress** and **decompress→decode** with **`--compression gzip|zstd`** (levels: **`--s1-gzip-level`** / **`--s1-zstd-level`**, defaults 6 / 3). **`S2`** (Phase 6) runs a **loopback mock** Schema Registry (`GET /schemas/ids/{id}`) and times **cold** (new TCP per fetch) vs **warm** (HTTP keep-alive) plus encode/round-trip with a warm GET before serialize; use **`--registry-schema-id`**. **`S3` / `S4`** (Phase 7) add **in-memory** producer (`batch_size` encodes + `bytes.join`) or consumer (prefetched payloads, batch decode) paths—**no Kafka client or broker**; use **`--batch-size`**. Phase-3 **`--gzip-level` / `--zstd-level`** remain separate **size probes** on raw wire (S2/S3/S4 ignore compression for timed codec path).
- **Formats:** `all` or comma-separated `avro,protobuf,json`. The CLI default is **`all`** (three codecs). If you pass e.g. **`--formats json`**, only that codec appears in `report.json` / `report.md`. Details: [Avro](#avro), [Protobuf](#protocol-buffers-protobuf).
- **Wire sizes (Phase 3):** `--gzip-level`, `--zstd-level` control size probes; optional `--confluent-envelope` / `--confluent-prefix-bytes` for Kafka-shaped value totals (independent of S1 timing compression).

Rubrics under `rubrics/` are merged into `report.json` when those files exist (default discovery from the current working directory). Each embedded rubric includes a pinned **`rubric_ref`** (e.g. `governance.v1`); **`rubric_index`** lists refs in the report. **`report.md`** includes an **appendix** with weights, checklist **evidence prompts**, and space for human scores.

Artifacts:

- `report.json` — machine-readable results (`report_version` **8**: S3/S4 **`scenario.s3_s4`**, **`batch_size`**, per-row **`s3_producer_batch`** / **`s4_consumer_batch`**; v7 S2; v6 limitations / integrity / regression; v5 S1), environment, fixture checksum, `measurement` / `allocations`.
- `report.md` — short human-readable summary, layer-cake notes, and Phase-8 appendix (limitations, artifact integrity, regression when enabled).

Optional regression hints (same scenario fingerprint as the baseline `report.json`):

```bash
ksp-bench run --scenario small --formats json --baseline-report reports/prior/report.json
```

## Avro

- **Library:** [fastavro](https://github.com/fastavro/fastavro) (see `pyproject.toml` for the pinned range).
- **Schemas:** JSON Avro definitions under `src/benchmark/fixtures/`:
  - `analytics_event_v2.avsc` — default writer/reader for most profiles.
  - `analytics_event_v1.avsc` — used with **`evolution`** profile: writer omits `new_field`, reader uses v2 (schema evolution path).
- **Wire format:** schemaless encode/decode in `benchmark.codecs.avro_codec` (no embedded writer schema in the benchmark bytes beyond what fastavro emits for that mode).
- **CLI:** include Avro in a run with `--formats avro` or `--formats all`. Reports list one result row per codec (e.g. **avro**) alongside protobuf and json.

## Protocol Buffers (Protobuf)

- **Library:** [protobuf](https://github.com/protocolbuffers/protobuf) Python runtime (pinned in `pyproject.toml`).
- **Schema:** `src/benchmark/fixtures/event.proto` — `AnalyticsEvent` and nested `EventContext`, aligned with the same logical fields as Avro/JSON fixtures.
- **Generated code:** `src/benchmark/fixtures/event_pb2.py` is checked in; the benchmark uses `SerializeToString` / `ParseFromString` via `benchmark.codecs.protobuf_codec`.
- **CLI:** include Protobuf with `--formats protobuf` or `--formats all`. Result rows use codec name **protobuf**.

### Regenerating `event_pb2.py`

If `event.proto` changes, regenerate stubs (dev venv; `grpcio-tools` is a **dev** extra, not a runtime dependency):

```bash
python -m grpc_tools.protoc \
  -I src/benchmark/fixtures \
  --python_out=src/benchmark/fixtures \
  src/benchmark/fixtures/event.proto
```

## Development

Use the [Makefile](Makefile) so local runs match CI. The first `make install` creates **`.venv/`** with `python3 -m venv` and installs into it (required on macOS/Homebrew Python, which blocks global `pip` under PEP 668).

```bash
make install   # create .venv if needed, then editable install with dev extras
make lint      # ruff, black --check, mypy (uses .venv)
make test      # pytest + CLI smoke (same as CI)
```

`make test` runs **`ksp-bench`** with **`--formats all`** for S0/S1 smokes, plus short **S2**–**S4** smokes (`json` for S2–S4), so reports under `/tmp/ksp-report` through `/tmp/ksp-s4` exercise those tiers.

To use another Python for creating the venv, run `python3.12 -m venv .venv` yourself, then `make install` (the existing `.venv` is reused).

Manual equivalents:

```bash
ruff check src tests
black src tests
mypy src
pytest -q
```

## Scope limits (today)

- **S2** is an optional **loopback mock** Schema Registry (`--tier S2`), not a live Confluent/Apicurio deployment. **S3/S4** are optional **in-memory** producer/consumer batch paths (`--tier S3`/`S4`, `--batch-size`), not a real Kafka client or broker.
- Governance and maintainability appear as **YAML rubrics** in reports, not auto-scored from benchmarks.
