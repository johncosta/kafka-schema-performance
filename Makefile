# Local installs use .venv (avoids PEP 668 "externally-managed-environment" on Homebrew Python).
# CI: setup-python provides python3; we create .venv with that interpreter and install into it.
VENV ?= .venv
PY := $(VENV)/bin/python

.PHONY: install lint test

$(PY):
	python3 -m venv $(VENV)

install: $(PY)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

lint: $(PY)
	$(PY) -m ruff check src tests
	$(PY) -m black --check src tests
	$(PY) -m mypy src

test: $(PY)
	$(PY) -m pytest -q
	$(VENV)/bin/ksp-bench run --scenario small --tier S0 --formats json --warmup 2 --iterations 5 --output-dir /tmp/ksp-report
	test -f /tmp/ksp-report/report.json
	$(VENV)/bin/ksp-bench run --scenario small --tier S1 --compression zstd --formats json --warmup 1 --iterations 3 --output-dir /tmp/ksp-s1
	test -f /tmp/ksp-s1/report.json
