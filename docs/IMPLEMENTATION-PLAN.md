# Implementation plan: benchmark utility (PRD)

**Status:** Draft  
**References:** [PRD-benchmark-utility.md](./PRD-benchmark-utility.md)  
**Last updated:** 2026-04-07  

This document turns the PRD into a **phased delivery plan**: repository shape, core abstractions, scenario tiers (S0–S4), reporting, and exit criteria per milestone. It is the working substitute for a full TDD until low-level design choices are locked.

---

## 1. Principles

1. **Layered scenarios first-class:** Every run declares a **scenario tier** (S0–S4) and a **layer cake** (what is measured vs explicitly excluded). Never emit a number without that context.
2. **Same logical data:** One canonical **domain model** (e.g. “analytics event” record) drives Avro, protobuf, and JSON encodings; generation uses a **fixed seed**.
3. **Pinned toolchain:** Dependencies and container images are **locked** (hashes/lockfiles); the report embeds versions and hardware OS summary.
4. **MVP before breadth:** Ship S0 + size/compression + reports + rubrics before mandatory real Kafka or live registry (optional toggles behind flags).

---

## 2. Decisions to lock early

**Repository status:** locked for the Python harness in this project.

| Decision | Choice |
|----------|--------|
| **Harness language** | **Python 3.11+** — package `benchmark` under `src/`, CLI **`ksp-bench`** (Typer) |
| **Libraries** | **fastavro**, **protobuf** (generated `event_pb2`), **orjson**, **zstandard** / **gzip** for tier S1 |
| **MVP scenario tiers** | **S0** (codec in-process) and **S1** (encode → compress → decompress → decode); **S2–S4** not implemented yet |
| **Registry** | Not wired; **rubrics** YAML attached to reports for governance / maintainability metadata |
| **Kafka in CI** | **None** (no producer/consumer path in default CI) |
| **Stats** | `time.perf_counter` samples; **p50/p90/p99**, mean, records/s, MB/s |

Fork / alternate stacks: use the same scenario labels; pin library versions in each report’s **environment** block.

| Decision | Options | Notes |
|----------|---------|-------|
| **Harness language** | Python / Java / Go | This repo implements **Python** first. |
| **Later tiers** | S2–S4 | Registry + Kafka-style paths per PRD §6.3. |
| **Stat engine** | Custom / pytest-benchmark / pyperf / JMH | This repo uses **custom** timers + JSON output. |

---

## 3. Repository layout (target)

```text
.
├── docs/
│   ├── PRD-benchmark-utility.md
│   └── IMPLEMENTATION-PLAN.md
├── src/                          # or python package root (adjust to tool choice)
│   └── benchmark/
│       ├── models/               # canonical in-memory domain types
│       ├── fixtures/             # schemas (.avsc, .proto), JSON samples
│       ├── codecs/               # AvroCodec, ProtobufCodec, JsonCodec (common interface)
│       ├── generate/             # synthetic record generators (seeded)
│       ├── scenarios/            # S0–S4 scenario builders + layer metadata
│       ├── metrics/              # timing, allocations (if any), size, compression
│       ├── report/               # JSON + Markdown renderers, rubric merge
│       └── cli.py                # single entrypoint
├── rubrics/
│   ├── governance.v1.yaml        # weighted criteria → scorecard input
│   └── maintainability.v1.yaml
├── tests/
└── pyproject.toml                # deps, ruff/mypy/pytest, optional [integration] extra
```

Language-specific names can replace `pyproject.toml` / `ruff` if the team chooses Java or Go; the **package boundaries** should stay the same.

---

## 4. Core abstractions

### 4.1 Codec adapter interface

Each format implements:

- **Serialize(domain → bytes)** and **Deserialize(bytes → domain)** (optionally **Deserialize(reader_schema, bytes)** for Avro evolution cases).
- **Schema artifacts:** paths or inlined schema strings for hashing in the report.
- **Wire metadata:** optional “envelope” builder (Confluent magic + schema id + payload) for S2+.

This isolates **fairness** rules (same domain in/out) from benchmark loops.

### 4.2 Scenario descriptor

Structured object / dict including:

- `tier`: S0 | S1 | S2 | S3 | S4  
- `payload_profile`: small | medium | large | evolution_*
- `formats`: avro | protobuf | json  
- `compression`: none | gzip | zstd (+ level)  
- `threads`, `warmup_iterations`, `timed_iterations`, `seed`  
- `layers_included` / `layers_excluded` (for the layer cake table)

### 4.3 Result schema (machine-readable)

Versioned JSON schema or Pydantic models for:

- Environment (hostname optional, OS, CPU model if available, library versions, git SHA, fixture checksum).  
- Per run: scenario descriptor + per-format **encode/decode/round-trip** stats, **size** stats, **compressed** stats.  
- Optional **phase timings** (encode % / decode % / validation %) when instrumentation exists.  
- **Governance / maintainability:** scores from rubric files + any manual overrides (never fabricate benchmark numbers).

---

## 5. Phased delivery

### Phase 0 — Scaffold and quality gates

- Package layout, dependency pins, `README` (how to run one scenario).
- CLI stub: `run --scenario small --formats all --tier S0 --output-dir reports/`.
- **Reproducibility:** collect versions; fail or warn if critical metadata missing (configurable).
- **CI:** lint + typecheck + unit tests on **non-benchmark** code (generators, report merge, checksums).
- **Makefile:** `make install`, `make lint`, `make test` (GitHub Actions runs the same targets). Local `make install` creates **`.venv`** and installs there (PEP 668–safe on Homebrew Python).
- **Pre-commit or CI:** format (e.g. black/ruff format).

**Exit:** CI green; `run --help` works; empty or placeholder report structure validates.

### Phase 1 — Fixtures and canonical payloads

- Define **three payload profiles** matching PRD §6.1 (small / medium / large) + at least one **evolution** case (added optional field).
- Check in **Avro `.avsc`**, **protobuf `.proto`**, and **JSON Schema** (or documented canonical JSON rules) for the same logical fields.
- **Generator:** build N records per profile with seeded RNG; optional fixed golden subset for regression tests.
- **Validation:** unit tests that round-trip domain → each format → domain for golden records.

**Exit:** Full matrix of schemas + generators; tests prove semantic equivalence for fixed samples.

### Phase 2 — S0 codec benchmarks

- Implement benchmark loop: warmup, timed iterations, optional multithreading (document thread model).
- Metrics: **records/s**, **MB/s**, **p50/p90/p99** for encode-only, decode-only, round-trip (PRD §6.1 + §6.1.1 where feasible).
- **Fine-grained timing:** use phase markers (encode start/stop, decode start/stop); document that validation may be merged with decode for some formats.
- **Allocations:** best-effort (e.g. Python `tracemalloc` delta per batch) — PRD allows “document limitation” if noisy.

**Exit:** MVP criterion (1) — single command runs **≥3 profiles × 3 formats** at S0; JSON + Markdown summary produced.

**Delivered:** `--scenario all` (small+medium+large) or comma-separated profiles; `report_version` **2** with `scenario.payload_profiles` and per-row `payload_profile`; `round_trip_mb_per_s`; Markdown lists p50/p90/p99 and records/s + MB/s for encode/decode/round-trip; `measurement` block documents timer, threading (single-threaded GIL), and phase boundaries; optional `--tracemalloc` single-sample peak (best-effort). Multithreading left documented-only for CPython.

### Phase 3 — Size, compression, cost formulas

- Per profile/format: mean/median/p95 **raw byte length**; same after **gzip** and **zstd** at declared levels.
- **Envelope overhead** helper: optional 5-byte Confluent header + 4-byte schema ID (configurable) included in “Kafka-shaped” size variant.
- Report section: **derived cost** formulas from PRD §6.2 with sensitivity sliders (±20% payload) as static static text or computed from measured mean.

**Exit:** MVP criterion (2) partial — size + compressed + tier labels; cost narrative present.

**Delivered:** Per codec row: `raw_encoded_bytes` (mean/median/p95 over timed encodes), `compressed_payload_bytes` for **gzip** and **zstd** at declared levels (scenario `size_and_cost`), ratios vs raw mean; optional `kafka_shaped` via Confluent-style value prefix (`--confluent-envelope`, configurable `--confluent-prefix-bytes`); `derived_cost` with PRD section 6.2 formula strings and ±20% mean-wire span. `report_version` **3**. Markdown summarizes the same.

### Phase 4 — Rubrics (governance & maintainability)

- Versioned YAML under `rubrics/` with **weights**, criteria, and **evidence prompts** (checklist, not synthetic timings).
- Renderer merges rubric scores into report **appendix**; rubric version pinned in output.
- Human review: rubrics are **human-scored** or semi-automated (e.g. “CI hook exists: yes/no”) — automation can come later.

**Exit:** MVP criterion (4) — published weights; each report references `governance.v1` / `maintainability.v1` (or current version).

### Phase 5 — S1 compression stack

- After encode, compress full payload; for decode path, decompress then decode (or symmetric definition documented).
- Label tier **S1**; include compression CPU/time in layer cake.

**Exit:** Clear S0 vs S1 comparison in report; no conflation of tiers.

### Phase 6 — S2 schema registry (optional integration)

- **Cold vs warm:** timed path for “fetch schema by ID” with empty client cache vs steady-state.
- **Implementation:** mock server with recorded latencies **or** Testcontainers SR; prefer one path for CI reproducibility.
- Confluent wire format encoding path if that is the deployment target.

**Exit:** Optional job or flag; documented setup; results always tagged **environment-specific**.

### Phase 7 — S3 / S4 Kafka client paths (optional)

- **S3:** Producer builds batches in memory (or to Testcontainers broker); measure client-side batch build + send flush (define exactly what is timed).
- **S4:** Consumer-style loop: prefetched bytes → deserialize batch; isolate broker fetch if possible.
- Run in **optional** CI or manual nightly; pin broker + client versions.

**Exit:** Layer cake states “real broker” vs “memory queue”; no default dependency for MVP developers.

### Phase 8 — Polish and regression

- Golden-run **thresholds** optional (warn if regression > X%) — format-specific baselines stored with caution.
- **Appendix:** limitations (hardware, OS thermal, background noise).
- SBOM or `pip list` / lockfile digest in report (PRD §7 artifact integrity).

**Exit:** MVP criterion (5) satisfied in default report template.

---

## 6. Testing strategy (meta)

| Layer | What to test |
|-------|----------------|
| **Generators** | Determinism from seed; field bounds; evolution variants. |
| **Codecs** | Golden round-trips; evolution case behavior. |
| **Stats** | Percentile helper against known tiny sample; monotonicity sanity. |
| **Report** | Snapshot or schema validation of JSON output; Markdown contains tier labels. |
| **Benchmarks** | Not run in default CI (noisy); optional scheduled job or `--quick` smoke (few iterations). |

---

## 7. Milestone → PRD MVP mapping

| PRD §8 MVP item | Milestone |
|-----------------|-----------|
| (1) Full matrix 3×3 | Phase 2 |
| (2) Throughput, percentiles, sizes, compressed, tier labels | Phases 2–3 + 5 |
| (3) Fine-grained breakdown or documented gap | Phase 2 (markers + narrative) |
| (4) Rubrics with weights | Phase 4 |
| (5) Limitations documented | Phase 8 |

---

## 8. Risk controls (implementation)

- **Noise:** Report **iteration count** and **confidence** (e.g. IQR or stdev); refuse “winner” language in templates.  
- **JSON canonicalization:** One serializer (`orjson` / `json` with `sort_keys=True` — pick one and document).  
- **Evolution fairness:** Same writer payloads; reader behavior defined per format (Avro `GenericDatumReader` vs specific classes — document).  

---

## 9. Next actions (checklist)

- [ ] Approve harness language and MVP tier scope (§2).  
- [ ] Create Phase 0 scaffold PR (branch from `main`).  
- [ ] Add `CONTRIBUTING.md` snippet: how to add a new payload profile.  
- [ ] After Phase 2: sample public report checked into `examples/` (redacted env) for review demos.  

---

## 10. Open items inherited from PRD

See PRD §9 **Open questions** (registry vendor, compliance for fixtures, Kafka in scope). Revisit after Phase 0 kickoff.
