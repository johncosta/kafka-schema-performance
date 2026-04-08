PYTHON ?= python3

.PHONY: install lint test

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check src tests
	black --check src tests
	mypy src

test:
	pytest -q
	ksp-bench run --scenario small --tier S0 --formats json --warmup 2 --iterations 5 --output-dir /tmp/ksp-report
	test -f /tmp/ksp-report/report.json
