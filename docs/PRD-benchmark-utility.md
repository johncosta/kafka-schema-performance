# PRD: Serialization Benchmark Utility (Avro, Protobuf, JSON)

**Document status:** Draft (gap-hardened)  
**Owner:** Platform / Data Engineering  
**Last updated:** 2026-04-11 *(test/evidence bar aligned with gap analysis)*  

---

## 1. Summary

Define a **benchmark utility and evaluation framework** that compares **Apache Avro**, **Protocol Buffers (protobuf)**, and **JSON** (typically UTF-8 text with optional compression) under workloads relevant to event streaming, APIs, and log pipelines—especially in **Kafka**-adjacent contexts. The utility must produce **reproducible** numbers and **structured reports** for **codec-level** performance (serialize/deserialize in isolation), **pipeline-level** performance (clients, compression, schema registry, and related stack), wire/storage footprint, and qualitative dimensions such as **schema governance** and **maintainability**.

**Evidence bar:** Any **comparative claim** surfaced in machine or human reports (tables, win-rates, HTML viz, narrative) must be **traceable** to (a) named scenario tiers and fixtures, (b) **dimension-isolated** metrics where the research question requires them (encode vs decode vs compress—not only round-trip unless explicitly labeled), and (c) automated tests or **golden artifacts** that pin semantics. **Fixture-specific** ordering assertions (e.g. “JSON wire exceeds binary for profile X”) are allowed only when labeled as **profile- and harness-dependent**, not as universal format truths.

This PRD describes *what* the service delivers, *how success is measured*, and *what evidence the test suite must eventually provide*; implementation details (language, harness libraries, CI layout) belong in the implementation plan / TDD and must not contradict Sections 8 and 11.

---

## 2. Problem statement

Teams choosing or migrating serialization formats need evidence beyond anecdotal claims. Raw micro-benchmarks often miss **schema evolution**, **registry operations**, **human workflows**, and **operational cost**. This project provides:

1. A **repeatable benchmark harness** with pinned versions and documented hardware assumptions.
2. A **metric catalog** aligned to engineering and platform concerns (performance, cost, governance, maintainability).
3. **Reporting artifacts** suitable for RFCs, architecture reviews, and capacity planning.

---

## 3. Goals and non-goals

### 3.1 Goals

- **Comparable runs:** Same payloads, schemas, and test matrix across Avro, protobuf, and JSON.
- **Observable performance:** Throughput and latency under defined concurrency and message shapes.
- **Efficiency signals:** Serialized size, compression ratios, and estimated network/storage cost models.
- **Governance lens:** Explicit criteria (not only benchmarks) for how each format behaves with **schema registries**, compatibility modes, and multi-team ownership.
- **Maintainability lens:** Documented qualitative factors (tooling, debugging, onboarding) with scoring rubrics where possible.
- **Dimension isolation:** The harness and tests must be able to separate **encode-only**, **decode-only**, **compress-only**, **decompress-only**, and **full pipeline** timings so conclusions are not silently dominated by one phase (Section 6.1.1, Section 11.1).
- **Causal evidence:** Where feasible, capture **why** a format leads or lags for a fixture: encoded size, compression ratio, allocation pressure, schema-resolution cost—not only aggregate round-trip (Section 11.2).

### 3.2 Non-goals (initial release)

- Declaring a single “winner” for all use cases; outcomes are **scenario-dependent**.
- Benchmarking every serializer implementation in every language (start with **one primary language** for the harness; optional secondary clients later).
- Replacing formal security review (schema injection, deserializer bombs) beyond noting **baseline threat considerations** in reports.
- Full cost attribution to cloud spend (provide **models and formulas**; actual billing integration is out of scope unless added later).
- **Universal cross-language performance laws** derived from this harness; any strict inequality (e.g. JSON wire > binary) is **fixture- and implementation-specific** unless measured across a declared matrix and still documented as environment-dependent.
- Pretending **mock** schema registry or **single-broker** Kafka exercises equal **production realism** to TLS, SASL, multi-broker, and real Confluent components—those are phased goals (Section 11.5–11.6).

### 3.3 Visualization and narrative discipline

- **Reports and HTML viz** may summarize win-rates and tier tables; they must **degrade safely** when optional `report.json` fields are absent and must not imply conclusions **not supported** by the scenario set that produced the report.
- **Automated tests** for viz SHALL progress beyond “string present” where practical: **golden** `report.json` fixtures with **hand-checked** win-rate or ranking expectations; tests that **win-rate math** matches canned inputs; tests that missing metrics do not render false “fastest” labels.
- **Glossary and layer-cake** copy must stay aligned with which tiers are **measured** vs **simulated** vs **absent** in a given run.

---

## 4. Users and stakeholders

| Role | Need |
|------|------|
| **Application engineers** | Pick a format with data for their latency/footprint budget. |
| **Data platform** | Standardize registries, CI checks, and breaking-change policy. |
| **SRE / capacity** | Estimate broker bandwidth, disk, and consumer CPU from serialization choice. |
| **Security / compliance** | Understand schema provenance and supply-chain/tooling implications. |

---

## 5. Service definition

### 5.1 What the “benchmark utility” is

A **versioned software package** (CLI and/or library) plus **fixtures** that:

1. **Loads** canonical test schemas and sample records (fixed + generated distributions).
2. **Serializes and deserializes** each record with Avro, protobuf, and JSON encoders **using pinned dependencies**.
3. **Executes** layered benchmark scenarios: **codec-only** (CPU/memory bound), **I/O-adjacent** (compression, registry HTTP), and **client integration** (producer/consumer batches where in scope)—each with documented batch size, threads, warm-up, iteration count, and seeds.
4. **Emits** machine-readable results (e.g. JSON) and human-readable summaries (e.g. Markdown/HTML).
5. **Optionally integrates** with schema registry–like flows (register schema, fetch ID, encode with schema ID) when those code paths are in scope for the deployment.

### 5.2 Interfaces (conceptual)

- **Input:** Scenario name, format profile (`avro` \| `protobuf` \| `json`), payload profile, concurrency, optional compression (none/gzip/zstd as applicable), seed for reproducibility.
- **Output:** Result bundle containing metrics (Section 6), environment metadata (CPU/OS/library versions), and checksum of inputs.

### 5.3 Quality requirements

- **Reproducibility:** Document seeds, versions, and hardware class; fail runs if version metadata cannot be collected.
- **Fairness:** Same logical payloads; avoid format-specific “cheating” (e.g. omitting unknown fields in one path only) unless the scenario explicitly tests that behavior.
- **Transparency:** Persist raw timing samples or histograms where feasible; summarize with percentiles (p50/p90/p99).
- **Configuration parity:** When comparing formats for a scenario, **fail or flag** mismatched configurations (e.g. generic Avro vs optimized protobuf) unless the scenario explicitly documents asymmetric modes.
- **Variance:** For timing-sensitive assertions, define **warmup policy** and acceptable **run-to-run variance** (or use deterministic canned timing inputs in unit tests) so CI does not encode flaky platform truth.

---

## 6. Measurement framework

### 6.1 Throughput and latency

**Objective:** Characterize CPU-bound serialization work and end-to-end paths that include optional registry round-trips.

| Metric | Definition | Notes |
|--------|------------|--------|
| **Serialize throughput** | Records (or MB) serialized per second | Warm-up excluded; report batch and thread counts. |
| **Deserialize throughput** | Records (or MB) deserialized per second | Include validation where applicable (Avro/schema evolution; protobuf optional unknown field behavior). |
| **Round-trip latency** | Time to serialize + deserialize one logical record | Report p50/p90/p99 over N iterations. |
| **Allocations / GC pressure** | (If available in harness language) Alloc rate, GC time | Critical for JVM/.NET runtimes; optional for native. |
| **Cold start** | First N operations after process start | Optional scenario for serverless-style deployments. |

**Scenarios (minimum set):**

- **Small event** (~200 bytes JSON equivalent): high cardinality fields, typical analytics envelope.
- **Medium nested** (~2–10 KB): nested structures, repeated fields, optional fields.
- **Large blob-heavy** (~100 KB+): string/binary heavy; stress copy and allocation behavior.
- **Schema evolution:** Reader/writer schema mismatch (add field, remove field, widen type if permitted) per format rules.

#### 6.1.1 Fine-grained serialization and deserialization

**Objective:** Isolate **what** is slow (encode vs decode vs validation vs allocation) so comparisons are actionable beyond a single “round-trip” number.

| Metric | Definition | Notes |
|--------|------------|--------|
| **Encode-only latency / throughput** | Serialize in-memory object → bytes (no I/O) | Separate from decode; report median and tail. |
| **Decode-only latency / throughput** | Bytes → in-memory object (no I/O) | Include parse + object materialization. |
| **Validation-bound path** | Extra checks after decode (required fields, numeric ranges, custom validators) | JSON Schema / hand-rolled checks vs Avro reader schema enforcement vs protobuf presence semantics. |
| **Schema resolution cost** | Time to bind reader/writer schema, build decoders, cache `GenericRecord` vs generated classes | One-time vs per-record; report both **first-use** and **steady-state**. |
| **UTF-8 / transcoding** | JSON text encode/decode vs binary field copy | Dominates small-string-heavy payloads. |
| **Allocation churn** | Bytes allocated per record, peak working set, optional **object pooling** effect | JVM: allocation rate + GC pause correlation; native: heap vs stack / arena if measured. |
| **Zero-copy vs copy semantics** | Whether decode returns views into input buffer vs copying | Affects large-string/binary fields and safety. |
| **Field access after decode** | Latency to read hot fields (flat record vs deeply nested) | Formats with lazy parsing (where applicable) vs eager materialization. |
| **Re-serialize stability** | Same logical value → identical bytes (canonical encodings) | Relevant for signing, caches, deduplication; note JSON normalization. |
| **Error-path cost** | Time to fail on corrupt/truncated payload | Security-relevant; optional micro-scenario. |

**Reporting:** Where the runtime allows, emit a **breakdown** (e.g. encode % / decode % / validation % of total CPU samples or wall time per phase). If only wall time is available, document measurement method (cooperative markers vs statistical sampling).

**Normative test alignment:** The pytest suite SHALL gain coverage over time so that **encode-only** and **decode-only** assertions exist per format for at least one fixture per tier where those phases are separable in the harness; round-trip-only checks are **insufficient** for the core research question (JSON faster encode / slower decode, compression masking codec cost, etc.). See Section 11.1.

### 6.2 Network and storage efficiency

**Objective:** Quantify bytes on the wire and on disk for representative payloads and compression strategies.

| Metric | Definition | Notes |
|--------|------------|--------|
| **Raw encoded size** | Byte length per record (mean/median/p95) | Uncompressed binary/text. |
| **Compressed size** | Same with gzip and/or zstd (levels documented) | JSON often benefits more; report fair compressor settings. |
| **Envelope overhead** | Magic bytes, schema ID, length prefixes, Kafka record headers | If benchmarking “Kafka-shaped” records, include realistic headers. |
| **Deduplication / dictionary effects** | (Optional) Repeated keys and shared schemas across batch | Especially relevant for columnar/compression in storage; note limitation for row-per-event. |

**Derived cost model (documented formulas, not billing integration):**

- **Network:** `egress_GB_month ≈ records_per_month × mean_wire_bytes × replication_factor × (topic fan-out if applicable)`.
- **Storage:** `retention_bytes ≈ records_per_day × mean_disk_bytes × retention_days × replication_factor`.

Reports should show **sensitivity**: e.g. ±20% payload size change impact on monthly GB.

### 6.3 Software stack and pipeline performance

**Objective:** Measure performance **outside** the pure codec that still scales with format choice: client libraries, batching, compression, schema discovery, and serialization-adjacent CPU in realistic pipelines. Results are **environment-specific**; the PRD requires labeling each scenario as **codec-only**, **codec + compression**, **codec + registry**, or **end-to-end client** so numbers are not conflated.

| Layer | Metric | Definition | Notes |
|-------|--------|------------|--------|
| **Compression** | Compress/decompress throughput & added latency | Bytes in/out per second; CPU per MB for gzip/zstd/snappy levels used in prod | Often dominates “small JSON” paths; pair with Section 6.2 sizes. |
| **Schema registry** | Register, lookup by ID, lookup latest, compatibility check | p50/p99 latency; throughput of **cached** vs **cold** schema fetch | HTTP/gRPC; connection reuse vs new connections per request. |
| **Serialization envelope** | Per-record overhead to attach schema ID, magic byte, length prefix | Nanoseconds or % of total produce path | Confluent wire format vs custom framing. |
| **Kafka producer** | Time to `send()` or equivalent for N records | Batch size, `linger.ms`, `batch.size`, acks; records/sec and client CPU | Optionally separate **serialize+partition** vs **full flush** depending on client API. |
| **Kafka consumer** | Poll loop time per batch; bytes fetched → records deserialized | Fetch size, `max.partition.fetch.bytes`; deser CPU per batch | Include **cooperative rebalance** cost only if scenario targets consumer churn. |
| **Threading / async** | Queue depth, executor saturation, event-loop delay | Relevant for async producers or gRPC streaming | Reports note single-thread vs multi-thread harness. |
| **TLS / networking** | (Optional) Handshake amortized over N messages; encrypted size | Isolate only when benchmark includes real TCP; otherwise out of scope and stated. |
| **Downstream serving** | (Optional) Same payload exposed over HTTP/gRPC: serialize-for-response | Compare JSON body vs protobuf `grpc` message framing | Extends “stack” to API edge without requiring Kafka. |

**Scenario taxonomies (examples):**

- **S0 — Codec in-process:** Sections 6.1–6.1.1 only; no network.
- **S1 — Codec + compress:** Encode/decode with on-heap buffers plus compress/decompress of full message bytes.
- **S2 — Codec + registry:** Include schema registration simulation or live registry; measure steady-state with warm schema cache vs explicit cache eviction.
- **S3 — Producer micro-benchmark:** Client serializes and builds batches to memory or loopback broker fixture (if available); measure client-side CPU and batch build time.
- **S4 — Consumer micro-benchmark:** Deserialize path from prefetched byte buffers (broker-independent) through to application object.

**Deliverable:** Report includes a **layer cake** diagram or table: for each scenario, which layers are included and which are explicitly excluded (e.g. “no TLS”, “no real broker”).

### 6.4 Schema governance across teams

**Objective:** Score how each format supports **multi-team evolution** with policy and automation. This is **partly qualitative**; the utility should capture **checklist scores** and **time-to-complete** tasks where measurable.

| Dimension | What to evaluate | Example evidence |
|-----------|------------------|------------------|
| **Compatibility guarantees** | BACKWARD / FORWARD / FULL semantics; accidental breakage modes | Matrix of allowed changes vs rejecting serializers. |
| **Registry coupling** | Dependency on Confluent/Apicurio/Glue-style registry | Steps to produce/consume with schema ID. |
| **CI integration** | Breaking-change detection in PRs | Can compat check run locally and in CI in &lt; 60s? |
| **Ownership boundaries** | Who can publish schema; namespaces; subject naming | Subject strategy (`topic-key`, `topic-value`, custom). |
| **Discoverability** | How consumers find “current” schema and changelog | Registry UI, Git-as-source-of-truth, codegen ownership. |
| **Polyglot codegen** | Quality of generated types across languages | protobuf typically strong; Avro varies; JSON often Schema + OpenAPI. |

**Deliverable:** A **governance scorecard** (weighted rubric) included in each report release, with versioned criteria so comparisons over time are meaningful.

### 6.5 Long-term system maintainability

**Objective:** Capture factors that affect **total cost of ownership** beyond μs per record.

| Dimension | Indicators |
|-----------|------------|
| **Debugging** | Human-readable payloads (JSON wins); binary formats need tools (hex, schema-aware dump). |
| **Tooling maturity** | Linters, IDE support, benchmarked plugins in observability stacks. |
| **Operational failure modes** | Schema ID mismatch, skewed producers, partial cluster upgrades. |
| **Hiring / onboarding** | Familiarity of typical hires; training material availability. |
| **Migration cost** | Path from JSON → binary or between binary formats (dual-write, replay). |
| **Supply chain** | Dependency footprint, license mix, security patch cadence for codecs/registries. |

**Deliverable:** A **maintainability rubric** (1–5 per category) with short rationale; optional survey hooks for internal teams later.

### 6.6 Test coverage, negative paths, and production realism (normative)

This section tightens the **evidence bar** between metrics (Section 6), reports/viz (Section 7), and the **pytest** suite. Items are **prioritized** so MVP can stay fast while the PRD records the full target.

#### 6.6.1 P0 — Dimension isolation and benchmark validity (highest priority)

- **Encode-only and decode-only** automated checks per format where the harness exposes separate timers; not only round-trip or scenario aggregates.
- **Compress-only / decompress-only** checks where S1 (or equivalent) separates timed compression from codec phases.
- **Explicit labeling** in tests and reports when compression or registry I/O dominates wall time so codec rankings are not over-interpreted.
- **Repeated-run variance / warmup:** document policy; add tests that metrics are **internally consistent** (e.g. canned timing inputs → expected aggregates) and CI smokes that do not encode platform-specific μs thresholds as universal truth.
- **Fixture-scoped inequalities:** any strict ordering (e.g. JSON wire larger than binary for profile P) MUST name **P**, **tier**, **compression level**, and **harness language**; MUST NOT be documented as a universal law.

#### 6.6.2 P1 — Causal evidence and payload diversity

- **Per-format:** encoded byte size, compression ratio, and (where the runtime allows) allocation or memory pressure—not only end-to-end winners.
- **Schema resolution:** distinguish **first-use** vs **steady-state** schema cost; tests that mock registry SHOULD simulate **cold vs warm** cache explicitly so “registry overhead” is not only a best-case HTTP loopback.
- **Payload matrix** beyond small/medium/large: deeply nested objects; high-cardinality repeated fields; sparse optional fields; many small scalars; large strings/blobs; numeric-heavy shapes; evolution cases (add/remove/rename); mixed nullability—so JSON-vs-binary conclusions are not an artifact of a single friendly shape.

#### 6.6.3 P1 — Negative and adversarial decode paths

Round-trip success on golden bytes is necessary but optimistic. The suite SHOULD add **expected-failure** cases: malformed payloads, truncated messages, wrong schema ID, incompatible evolution, unknown fields, invalid UTF-8 where applicable, partial decompression failure—so a format cannot appear “fast” by skipping validation or failing open.

#### 6.6.4 P2 — Schema registry production realism

Beyond **mock** registry HTTP (S2): phased tests or integration environments for **real** Confluent-compatible registry (or declared alternative), serializer client caching, auth/TLS, retry/backoff, compatibility mode effects, and **registry unavailable** behavior. Mock paths remain valuable but MUST be labeled as non-production in reports.

#### 6.6.5 P2 — Kafka production realism

Current **single happy-path** broker produce/consume proves wiring, not operational equivalence. Phase in: TLS, SASL, multi-broker, partitioned topics, varying batch sizes, key vs value serialization, producer acks modes, idempotent producer settings, client- vs broker-level compression interactions, consumer lag or end-to-end latency metrics where feasible, rebalance/retry stress, **large-message** boundaries, backpressure, **poison messages** / DLQ expectations. Each addition MUST appear in the layer-cake / limitations text for the run.

#### 6.6.6 Under-asserted metrics (explicit backlog)

Until covered, reports SHOULD surface these as **N/A** or **not measured** rather than implying coverage: p95/p99 (not only mean), throughput under sustained load, compression ratio per tier, decode error rates, consumer lag, reproducibility across repeated runs, strict variance thresholds.

#### 6.6.7 Visualization and report semantics (tests)

- **Golden `report.json`** (and selective HTML) fixtures with hand-checked expectations for win-rate, rankings, and “fastest” labels.
- **Math tests** for win-rate and comparison tables from known inputs.
- **Safe degradation** when optional fields are missing—no fabricated rankings.

#### 6.6.8 CI without Docker (required path)

Provide a **narrow in-process** suite with deterministic inputs, **canned timing** or micro-benchmarks bounded by variance rules, **mock** Kafka transport for producer/consumer/report-merge logic where applicable, and golden validation—so **meaningful CI** runs on hosts without Kafka or Testcontainers, while broker tests remain optional or scheduled.

---

## 7. Reporting and comparability

- **Baseline report:** Table comparing the three formats across all scenarios with **confidence intervals** or percentile spread where possible.
- **Narrative appendix:** Governance and maintainability scorecards with references to internal standards.
- **Artifact integrity:** Hash of fixture inputs; list of dependency versions (SBOM optional follow-up).
- **Honest scope:** Each release notes which Section **6.6** priorities are implemented vs backlog; HTML viz and summary win-rates MUST align with that scope (Section 3.3).

---

## 8. Success criteria (MVP)

1. Single-command (or CI job) reproduces a **full matrix** for at least three payload profiles and three formats.
2. Published report includes **throughput, latency percentiles, size stats, compressed size stats**, and **codec-only vs layered scenarios** clearly labeled (Section 6.3).
3. Where supported by the harness, reports include **fine-grained serialize/decode/validation** breakdown (Section 6.1.1) or a documented reason (e.g. runtime limits).
4. Governance and maintainability sections use a **published rubric** with explicit weights.
5. Documentation states **limitations** (single-node CPU, which stack layers are real vs simulated, no cross-region latency unless run says otherwise).
6. **In repo:** `tests/test_runner.py` asserts distinct **encode** and **decode** means on S0 rows; **S1** rows include **`s1_phase_isolation`** (compress-only, decompress-only, codec encode-only, decode-from-raw-wire) with tests and Markdown; `tests/test_metrics_stats_canned.py` pins **percentile math**; `tests/test_codecs_negative_decode.py` covers **expected-failure** decodes and **invalid UTF-8 JSON** / **garbage zstd** (Section 6.6.1). Canned wall-clock aggregates for combined paths remain optional backlog.
7. **In repo:** `examples/reports/golden_two_codecs.report.json` plus `tests/test_golden_report_win_rate.py` and **`aggregate_codec_win_rates`** in `benchmark.viz.summary_html` validate **win-rate math** and summary HTML for that fixture (Section 6.6.7).
8. **In repo:** **`make test-ci`** (pytest `-m "not kafka"` + `ksp-bench` S0–S4 smokes) is the **default CI** path without Docker; **`make test`** runs Kafka E2E when Docker is available (Section 6.6.8).

---

## 9. Risks and open questions

| Risk | Mitigation |
|------|------------|
| Benchmark results are misread as universal truth | Lead with scenario labels; forbid “winner” language in auto-summary. |
| Library choice dominates outcome | Pin versions; consider pluggable codecs; document defaults. |
| JSON ambiguity (floats, field order, Unicode) | Define canonical JSON generation; use a reference serializer. |
| Registry or network noise dominates | Separate **S0–S4** (or equivalent) scenario tiers; never compare codec-only to end-to-end without labeling. |
| Stack benchmarks are environment-specific | Pin client, broker, and OS versions; report hardware class; avoid cross-repo numeric targets. |
| **Hard-coded inequalities** (e.g. JSON wire > binary) encode harness bias | Restrict to **named fixtures**; label as non-universal; prefer structural metric tests + variance policy (Sections 3.2, 6.6.1). |
| **“Fast default pytest”** implies deep correctness | Document smoke vs deep tiers; expand Section 6.6 backlog in implementation plan; keep summary viz scope honest (Section 3.3). |
| **Viz exceeds tested semantics** | Golden reports; math tests; safe missing-field behavior (Section 6.6.7). |
| **Mock registry / single broker** imply production realism | Layer-cake + limitations text; phase P2 scenarios (Sections 6.6.4–6.6.5). |
| **Compression masks codec story** | Report encode/decode/compress fractions; separate tests (Sections 6.1.1, 6.6.1). |
| **Python runtime effects** (C-accelerated JSON vs wrapper-heavy Avro) | Document in limitations; consider secondary harness language (Open questions). |

**Open questions**

- Primary harness language (Python / Java / Go)?
- Kafka client in scope for first release or “codec-only” first?
- Target registry (Confluent Schema Registry vs others)?
- Compliance needs (PII in fixtures—use synthetic data only)?

---

## 10. Out of scope for this PRD

Low-level implementation architecture and repository layout remain in the **implementation plan** and/or **TDD**. **Normative test and evidence requirements** for benchmarking are now part of this PRD (**Section 6.6**, **Section 3.3**, **Section 8 items 6–8**); the implementation plan MUST trace deliverables to those sections.

---

## Appendix A: Glossary

- **Wire format:** Bytes as consumed by the network or storage layer, possibly with framing.
- **Schema evolution:** Ability for readers and writers at different schema versions to interoperate safely under declared compatibility rules.
- **Governance:** Process and tooling that prevents incompatible schema publishes and clarifies ownership.

---

## Appendix B: Example metric snapshot (illustrative only)

| Scenario | Format | Encode MB/s | Decode MB/s | p99 round-trip µs | p99 encode µs | p99 decode µs | Mean bytes (raw) | Mean bytes (zstd) | Scenario tier (S0–S4) |
|----------|--------|-------------|-------------|-------------------|---------------|---------------|------------------|-------------------|-------------------------|
| Small event | … | … | … | … | … | … | … | … | … |

*(Placeholder—real values come from the harness. Split encode/decode columns are required once Section 6.6.1 P0 coverage is met; until then reports must state the gap explicitly.)*
