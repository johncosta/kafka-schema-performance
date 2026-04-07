# PRD: Serialization Benchmark Utility (Avro, Protobuf, JSON)

**Document status:** Draft  
**Owner:** Platform / Data Engineering  
**Last updated:** 2026-04-07  

---

## 1. Summary

Define a **benchmark utility and evaluation framework** that compares **Apache Avro**, **Protocol Buffers (protobuf)**, and **JSON** (typically UTF-8 text with optional compression) under workloads relevant to event streaming, APIs, and log pipelines—especially in **Kafka**-adjacent contexts. The utility must produce **reproducible** numbers and **structured reports** for throughput, latency, wire/storage footprint, and qualitative dimensions such as **schema governance** and **maintainability**.

This PRD describes *what* the service delivers and *how success is measured*; implementation details (language, harness libraries, CI) belong in a separate technical specification after this PRD is accepted.

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

### 3.2 Non-goals (initial release)

- Declaring a single “winner” for all use cases; outcomes are **scenario-dependent**.
- Benchmarking every serializer implementation in every language (start with **one primary language** for the harness; optional secondary clients later).
- Replacing formal security review (schema injection, deserializer bombs) beyond noting **baseline threat considerations** in reports.
- Full cost attribution to cloud spend (provide **models and formulas**; actual billing integration is out of scope unless added later).

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
3. **Executes** benchmark scenarios (batch size, threads, warm-up, iteration count, optional simulated I/O).
4. **Emits** machine-readable results (e.g. JSON) and human-readable summaries (e.g. Markdown/HTML).
5. **Optionally integrates** with schema registry–like flows (register schema, fetch ID, encode with schema ID) when those code paths are in scope for the deployment.

### 5.2 Interfaces (conceptual)

- **Input:** Scenario name, format profile (`avro` \| `protobuf` \| `json`), payload profile, concurrency, optional compression (none/gzip/zstd as applicable), seed for reproducibility.
- **Output:** Result bundle containing metrics (Section 6), environment metadata (CPU/OS/library versions), and checksum of inputs.

### 5.3 Quality requirements

- **Reproducibility:** Document seeds, versions, and hardware class; fail runs if version metadata cannot be collected.
- **Fairness:** Same logical payloads; avoid format-specific “cheating” (e.g. omitting unknown fields in one path only) unless the scenario explicitly tests that behavior.
- **Transparency:** Persist raw timing samples or histograms where feasible; summarize with percentiles (p50/p90/p99).

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

### 6.3 Schema governance across teams

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

### 6.4 Long-term system maintainability

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

---

## 7. Reporting and comparability

- **Baseline report:** Table comparing the three formats across all scenarios with **confidence intervals** or percentile spread where possible.
- **Narrative appendix:** Governance and maintainability scorecards with references to internal standards.
- **Artifact integrity:** Hash of fixture inputs; list of dependency versions (SBOM optional follow-up).

---

## 8. Success criteria (MVP)

1. Single-command (or CI job) reproduces a **full matrix** for at least three payload profiles and three formats.
2. Published report includes **throughput, latency percentiles, size stats, compressed size stats**.
3. Governance and maintainability sections use a **published rubric** with explicit weights.
4. Documentation states **limitations** (single-node CPU, no cross-region latency, etc.).

---

## 9. Risks and open questions

| Risk | Mitigation |
|------|------------|
| Benchmark results are misread as universal truth | Lead with scenario labels; forbid “winner” language in auto-summary. |
| Library choice dominates outcome | Pin versions; consider pluggable codecs; document defaults. |
| JSON ambiguity (floats, field order, Unicode) | Define canonical JSON generation; use a reference serializer. |
| Registry latency dominates | Separate “pure codec” vs “registry-inclusive” scenarios. |

**Open questions**

- Primary harness language (Python / Java / Go)?
- Kafka client in scope for first release or “codec-only” first?
- Target registry (Confluent Schema Registry vs others)?
- Compliance needs (PII in fixtures—use synthetic data only)?

---

## 10. Out of scope for this PRD

Implementation architecture, repository layout, and test plan are specified in a follow-on **Technical Design Document (TDD)** after goals and metrics are ratified.

---

## Appendix A: Glossary

- **Wire format:** Bytes as consumed by the network or storage layer, possibly with framing.
- **Schema evolution:** Ability for readers and writers at different schema versions to interoperate safely under declared compatibility rules.
- **Governance:** Process and tooling that prevents incompatible schema publishes and clarifies ownership.

---

## Appendix B: Example metric snapshot (illustrative only)

| Scenario | Format | Serialize MB/s | p99 round-trip µs | Mean bytes (uncompressed) | Mean bytes (zstd) |
|----------|--------|----------------|-------------------|---------------------------|-------------------|
| Small event | … | … | … | … | … |

*(Placeholder—real values come from the harness.)*
