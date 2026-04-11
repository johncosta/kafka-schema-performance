# Local installs use .venv (avoids PEP 668 "externally-managed-environment" on Homebrew Python).
# CI: setup-python provides python3; we create .venv with that interpreter and install into it.
VENV ?= .venv
PY := $(VENV)/bin/python

# CLI smoke: all payload profiles (incl. evolution), all codecs, gzip + zstd per tier.
SCENARIOS := small,medium,large,evolution
FORMATS := all

COMPOSE_KAFKA := docker/docker-compose.kafka.yml
KAFKA_ENV := KSP_KAFKA_BOOTSTRAP=127.0.0.1:19092 KSP_KAFKA_BROKER_LABEL=redpanda_compose

.PHONY: install lint test test-kafka report

$(PY):
	python3 -m venv $(VENV)

install: $(PY)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev,kafka]"

lint: $(PY)
	$(PY) -m ruff check src tests
	$(PY) -m black --check src tests
	$(PY) -m mypy src

# Full pytest (in-process + @pytest.mark.distributed + Kafka E2E) then CLI matrix.
# Requires Docker for Redpanda (docker/docker-compose.kafka.yml).
test: $(PY)
	docker compose -f $(COMPOSE_KAFKA) up -d
	$(PY) scripts/wait_for_tcp.py --host 127.0.0.1 --port 19092 --timeout 90 \
		|| (docker compose -f $(COMPOSE_KAFKA) down; exit 1)
	$(KAFKA_ENV) $(PY) -m pytest -q; py_ec=$$?; docker compose -f $(COMPOSE_KAFKA) down; \
		if [ $$py_ec -ne 0 ]; then exit $$py_ec; fi
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S0 --formats $(FORMATS) --compression zstd --warmup 2 --iterations 5 --output-dir /tmp/ksp-s0-zstd
	test -f /tmp/ksp-s0-zstd/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S0 --formats $(FORMATS) --compression gzip --warmup 2 --iterations 5 --output-dir /tmp/ksp-s0-gzip
	test -f /tmp/ksp-s0-gzip/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S1 --compression zstd --formats $(FORMATS) --warmup 1 --iterations 3 --output-dir /tmp/ksp-s1-zstd
	test -f /tmp/ksp-s1-zstd/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S1 --compression gzip --formats $(FORMATS) --warmup 1 --iterations 3 --output-dir /tmp/ksp-s1-gzip
	test -f /tmp/ksp-s1-gzip/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S2 --compression zstd --formats $(FORMATS) --warmup 1 --iterations 3 --output-dir /tmp/ksp-s2-zstd
	test -f /tmp/ksp-s2-zstd/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S2 --compression gzip --formats $(FORMATS) --warmup 1 --iterations 3 --output-dir /tmp/ksp-s2-gzip
	test -f /tmp/ksp-s2-gzip/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S3 --compression zstd --formats $(FORMATS) --batch-size 8 --warmup 1 --iterations 2 --output-dir /tmp/ksp-s3-zstd
	test -f /tmp/ksp-s3-zstd/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S3 --compression gzip --formats $(FORMATS) --batch-size 8 --warmup 1 --iterations 2 --output-dir /tmp/ksp-s3-gzip
	test -f /tmp/ksp-s3-gzip/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S4 --compression zstd --formats $(FORMATS) --batch-size 8 --warmup 1 --iterations 2 --output-dir /tmp/ksp-s4-zstd
	test -f /tmp/ksp-s4-zstd/report.json
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier S4 --compression gzip --formats $(FORMATS) --batch-size 8 --warmup 1 --iterations 2 --output-dir /tmp/ksp-s4-gzip
	test -f /tmp/ksp-s4-gzip/report.json

# Kafka integration tests only (compose up → pytest -m kafka → compose down).
test-kafka: $(PY)
	docker compose -f $(COMPOSE_KAFKA) up -d
	$(PY) scripts/wait_for_tcp.py --host 127.0.0.1 --port 19092 --timeout 90 \
		|| (docker compose -f $(COMPOSE_KAFKA) down; exit 1)
	$(KAFKA_ENV) $(PY) -m pytest tests/integration -m kafka -v; py_ec=$$?; \
		docker compose -f $(COMPOSE_KAFKA) down; exit $$py_ec

# Full test suite first, then a repo-local benchmark + stack HTML (output is gitignored under reports/).
report: test
	$(VENV)/bin/ksp-bench run --scenario $(SCENARIOS) --tier all --formats $(FORMATS) --compression zstd --warmup 3 --iterations 15 --batch-size 8 --output-dir reports/make-report
	test -f reports/make-report/report.json
	$(VENV)/bin/ksp-bench viz reports/make-report/report.json -o reports/make-report/stack.html
	test -f reports/make-report/summary.html
	@echo "Wrote reports/make-report/report.json report.md stack.html summary.html"
