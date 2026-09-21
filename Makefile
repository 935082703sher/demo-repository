PYTHON ?= python3.12
UVICORN ?= uvicorn
RUFF ?= ruff
MYPY ?= mypy
PYTEST ?= pytest

.PHONY: install format format-check lint typecheck test pii-check run check demo

install:
	$(PYTHON) -m pip install -e '.[dev]'

format:
	$(RUFF) format app tests evaluations

format-check:
	$(RUFF) format --check app tests evaluations

lint:
	$(RUFF) check app tests evaluations

typecheck:
	$(MYPY) app tests evaluations

test:
	$(PYTEST)

pii-check:
	$(PYTHON) -m app.services.privacy_scan app/data evaluations/cases

run:
	$(UVICORN) app.main:app --host 127.0.0.1 --port 8000

check: format-check lint typecheck test pii-check

demo:
	docker compose up --build
