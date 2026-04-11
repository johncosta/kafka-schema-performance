# Contributing

## Local checks

Use the [Makefile](Makefile) so results match CI:

- `make install` — editable install with dev and Kafka extras (`.venv/`).
- `make lint` — Ruff, Black `--check`, Mypy on `src/`.
- `make test-ci` — full pytest **excluding** `@pytest.mark.kafka`, then `ksp-bench` smokes for S0–S4 (no Docker). This is what GitHub Actions runs.
- `make test` — same as `make test-ci`, plus Docker Compose Kafka, full pytest **including** Kafka E2E, then the CLI smokes again. Requires Docker.

Kafka-only integration tests: `make test-kafka` (Compose up → `pytest tests/integration -m kafka` → Compose down).

## Adding a payload profile

Profiles are the `PayloadProfile` enum and the `sample_event()` / golden helpers in `src/benchmark/generate/records.py`.

1. Add a new `PayloadProfile` member (string value is the CLI/report label).
2. Implement a branch in `sample_event()` that returns a representative `AnalyticsEvent` for that profile (use the profile’s `rng` for deterministic fields).
3. Add `golden_<name>_event()` if regression tests need a fixed record; keep it aligned with [JSON Schema](src/benchmark/fixtures/) and Avro/Protobuf fixtures where applicable.
4. Extend Avro `.avsc` / `event.proto` / JSON schema only if the logical shape changes; regenerate `event_pb2.py` when `.proto` changes (see README).
5. Add unit tests: round-trip for all codecs on `sample_event(NewProfile, seed=…)` and any golden path; optionally extend `tests/test_runner.py` matrix if the profile must appear in exhaustive `build_report` tests.

Run `make test-ci` before opening a PR.
