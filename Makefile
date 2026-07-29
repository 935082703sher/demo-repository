PYTHON ?= python3.12
UVICORN ?= uvicorn
RUFF ?= ruff
MYPY ?= mypy
PYTEST ?= pytest

.PHONY: install format format-check lint typecheck test run check

install:
	$(PYTHON) -m pip install -e '.[dev]'

format:
	$(RUFF) format app tests

format-check:
	$(RUFF) format --check app tests

lint:
	$(RUFF) check app tests

typecheck:
	$(MYPY) app tests

test:
	$(PYTEST)

run:
	$(UVICORN) app.main:app --host 127.0.0.1 --port 8000

check: format-check lint typecheck test
