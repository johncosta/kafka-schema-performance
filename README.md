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
```

- **Profiles:** `small`, `medium`, `large`, `evolution` (Avro uses schema v1 → v2 for evolution).
- **Tiers:** `S0` codec only; `S1` adds **gzip** or **zstd** around the encoded bytes (`--compression`).
- **Formats:** `all` or comma-separated `avro,protobuf,json`.

Rubrics under `rubrics/` are merged into `report.json` when those files exist (default discovery from the current working directory).

Artifacts:

- `report.json` — machine-readable results, environment versions, fixture checksum, optional rubrics.
- `report.md` — short human-readable summary and layer-cake notes.

## Protobuf code generation

If `event.proto` changes, regenerate `src/benchmark/fixtures/event_pb2.py`:

```bash
python -m grpc_tools.protoc \
  -I src/benchmark/fixtures \
  --python_out=src/benchmark/fixtures \
  src/benchmark/fixtures/event.proto
```

(`grpcio-tools` is not a runtime dependency; use a dev venv.)

## Development

Use the [Makefile](Makefile) so local runs match CI:

```bash
make install   # upgrade pip + editable install with dev extras
make lint      # ruff, black --check, mypy
make test      # pytest + CLI smoke (same as CI)
```

Override the interpreter if needed: `PYTHON=python3 make install` (default is `python3`).

Manual equivalents:

```bash
ruff check src tests
black src tests
mypy src
pytest -q
```

## Scope limits (today)

- No live **schema registry** or **Kafka** client in the default path; tiers **S2–S4** are future work.
- Governance and maintainability appear as **YAML rubrics** in reports, not auto-scored from benchmarks.
