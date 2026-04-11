# Local installs use .venv (avoids PEP 668 "externally-managed-environment" on Homebrew Python).
# CI: setup-python provides python3; we create .venv with that interpreter and install into it.
VENV ?= .venv
PY := $(VENV)/bin/python

.PHONY: install lint test report

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
	$(VENV)/bin/ksp-bench run --scenario small,medium,large,evolution --tier S0 --formats all --warmup 2 --iterations 5 --output-dir /tmp/ksp-report
	test -f /tmp/ksp-report/report.json
	$(VENV)/bin/ksp-bench run --scenario small --tier S1 --compression zstd --formats all --warmup 1 --iterations 3 --output-dir /tmp/ksp-s1-zstd
	test -f /tmp/ksp-s1-zstd/report.json
	$(VENV)/bin/ksp-bench run --scenario small --tier S1 --compression gzip --formats all --warmup 1 --iterations 3 --output-dir /tmp/ksp-s1-gzip
	test -f /tmp/ksp-s1-gzip/report.json
	$(VENV)/bin/ksp-bench run --scenario small --tier S2 --formats json --warmup 1 --iterations 3 --output-dir /tmp/ksp-s2
	test -f /tmp/ksp-s2/report.json
	$(VENV)/bin/ksp-bench run --scenario small --tier S3 --formats json --batch-size 8 --warmup 1 --iterations 2 --output-dir /tmp/ksp-s3
	test -f /tmp/ksp-s3/report.json
	$(VENV)/bin/ksp-bench run --scenario small --tier S4 --formats json --batch-size 8 --warmup 1 --iterations 2 --output-dir /tmp/ksp-s4
	test -f /tmp/ksp-s4/report.json

# Full test suite first, then a repo-local benchmark + stack HTML (output is gitignored under reports/).
report: test
	$(VENV)/bin/ksp-bench run --scenario small,medium,large,evolution --tier S0 --formats all --warmup 5 --iterations 30 --output-dir reports/make-report
	test -f reports/make-report/report.json
	$(VENV)/bin/ksp-bench viz reports/make-report/report.json -o reports/make-report/stack.html
	@echo "Wrote reports/make-report/report.json report.md stack.html"
