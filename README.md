# RTMC AI Assistant — Demo 1 Backend

A controlled local FastAPI foundation for RTMC citizen guidance and complaint-draft
preparation. It proves the API and safety workflow expected by the RTMC Nuxt website;
the frontend itself is intentionally outside this repository.

Demo 1 uses:

- Pydantic v2 request and response models;
- deterministic Uzbek, Russian, and English category rules;
- deterministic input and output guardrails;
- local synthetic knowledge explicitly marked `demo_only`;
- a mock language-provider implementation with no network access;
- process-local sessions, draft versions, consent records, and idempotency state.

> **Safety boundary:** This demo is not production-ready. It cannot register an
> official appeal, generate an official case number, track status, or store real
> citizen data. All in-memory data disappears when the process restarts.

## Prerequisites

- Python 3.12
- GNU Make (optional; commands can be run directly)
- Docker with Compose (optional)

The local path used for a Python virtual environment must not contain a colon on
platforms where Python treats `:` as a path separator.

## Local installation and execution

```bash
python3.12 -m venv /tmp/rtmc-ai-assistant-venv
. /tmp/rtmc-ai-assistant-venv/bin/activate
pip install -e '.[dev]'
make check
make run
```

Open:

- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>
- Health: <http://127.0.0.1:8000/health>

Example:

```bash
curl -s http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"language":"uz","message":"Mening mobil internetim juda sekin"}'
```

## Docker

```bash
docker compose build
docker compose up -d
curl -s http://127.0.0.1:8000/health
docker compose down
```

The image runs as a non-root user and includes a health check. It has no database,
secret, or official RTMC integration.

## Repository map

```text
app/api/         thin FastAPI routes
app/core/        settings, errors, safe logging
app/domain/      typed enums and schemas
app/providers/   small provider interface and deterministic mock
app/services/    workflow, guardrails, retrieval, drafts, handoff
app/data/        synthetic local demo fixture
tests/           deterministic API and service regression tests
docs/            scope, architecture, contract, security, tests, next phases
```

See [`docs/DEMO_SCOPE.md`](docs/DEMO_SCOPE.md),
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) before integration work.

Completion evidence is recorded in
[`docs/DEMO_1_COMPLETION_EVIDENCE.md`](docs/DEMO_1_COMPLETION_EVIDENCE.md).
