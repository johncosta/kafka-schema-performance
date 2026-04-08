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
- **Tiers:** `S0` codec only; `S1` times **encode→compress** and **decompress→decode** with **`--compression gzip|zstd`** (levels: **`--s1-gzip-level`** / **`--s1-zstd-level`**, defaults 6 / 3). Phase-3 **`--gzip-level` / `--zstd-level`** remain separate **size probes** on raw wire.
- **Formats:** `all` or comma-separated `avro,protobuf,json`. The CLI default is **`all`** (three codecs). If you pass e.g. **`--formats json`**, only that codec appears in `report.json` / `report.md`.
- **Wire sizes (Phase 3):** `--gzip-level`, `--zstd-level` control size probes; optional `--confluent-envelope` / `--confluent-prefix-bytes` for Kafka-shaped value totals (independent of S1 timing compression).

Rubrics under `rubrics/` are merged into `report.json` when those files exist (default discovery from the current working directory). Each embedded rubric includes a pinned **`rubric_ref`** (e.g. `governance.v1`); **`rubric_index`** lists refs in the report. **`report.md`** includes an **appendix** with weights, checklist **evidence prompts**, and space for human scores.

Artifacts:

- `report.json` — machine-readable results (`report_version` **6**: adds **`limitations`**, **`artifact_integrity`** (sorted `pip freeze` + SHA-256), optional **`regression_check`** when **`--baseline-report`** is set; still includes v5 S1 fields, rubrics, sizes), environment, fixture checksum, `measurement` / `allocations`.
- `report.md` — short human-readable summary, layer-cake notes, and Phase-8 appendix (limitations, artifact integrity, regression when enabled).

Optional regression hints (same scenario fingerprint as the baseline `report.json`):

```bash
ksp-bench run --scenario small --formats json --baseline-report reports/prior/report.json
```

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

Use the [Makefile](Makefile) so local runs match CI. The first `make install` creates **`.venv/`** with `python3 -m venv` and installs into it (required on macOS/Homebrew Python, which blocks global `pip` under PEP 668).

```bash
make install   # create .venv if needed, then editable install with dev extras
make lint      # ruff, black --check, mypy (uses .venv)
make test      # pytest + CLI smoke (same as CI)
```

`make test` runs **`ksp-bench`** with **`--formats all`**, so smoke reports under `/tmp/ksp-report` and `/tmp/ksp-s1` include **avro**, **protobuf**, and **json** (not JSON-only).

To use another Python for creating the venv, run `python3.12 -m venv .venv` yourself, then `make install` (the existing `.venv` is reused).

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
