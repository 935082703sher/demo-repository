# RTMC AI Assistant — Demo 2 Backend

A controlled internal FastAPI demonstration for grounded RTMC guidance and
complaint-draft preparation. It extends the frozen Demo 1 API without adding an
official appeal integration or production frontend.

Demo 2 uses:

- Pydantic v2 request and response models;
- deterministic Uzbek, Russian, and English category rules;
- deterministic input, scope, output, and citation guardrails;
- strict approved-knowledge metadata and local synthetic records marked `demo_only`;
- separate process-local LLM quotas and request-rate protection;
- a provider-independent boundary with mock default and a disabled-by-default OpenAI
  Responses adapter;
- structured provider output, bounded retries, token/cost/latency measurements;
- process-local sessions, draft versions, consent records, and idempotency state.
- a repeatable 60-case multilingual synthetic evaluation suite.

> **Safety boundary:** Demo 2 is not production-ready. It cannot register an
> official appeal, generate an official case number, track status, or store real
> citizen data. The default provider makes no network call. All in-memory data
> disappears when the process restarts.

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
python -m evaluations.run
make run
```

Open:

- Demo test page: <http://127.0.0.1:8000/>
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

Or the one-command demo path:

```bash
make demo
```

which runs `docker compose up --build` and opens the API on
<http://127.0.0.1:8000/> (demo page) once healthy.

The image runs as a non-root user and includes a health check. It has no database,
committed secret, or official RTMC integration.

## Configuration

Copy `.env.example` to `.env` only when local overrides are required. Important Demo 2
settings include:

- `LLM_PROVIDER=mock` (default) — deterministic, no network call. `openai` remains
  disabled without a key. `ollama` runs a real self-hosted local model with no external
  API and no key required — see [`docs/LOCAL_LLM.md`](docs/LOCAL_LLM.md);
- `LLM_GENERATION_LIMIT_PER_SESSION=10`;
- `LLM_QUOTA_WINDOW_SECONDS=86400`;
- `REQUEST_RATE_LIMIT_PER_MINUTE=20`;
- optional approved support phone/contact URL;
- optional external provider model/key, timeout, retries, and cost rates;
- `CORS_ALLOWED_ORIGINS` for local website integration (defaults to common Nuxt/Vite
  dev ports; empty disables CORS entirely).

Do not configure a real external provider without RTMC authorization. No model or API
key is committed. Self-hosted local inference (Ollama) requires no API key at all.

## Repository map

```text
app/api/         thin FastAPI routes
app/core/        settings, errors, safe logging
app/domain/      typed enums and schemas
app/providers/   provider interface, mock, configured adapter
app/repositories process-local replaceable usage/rate storage
app/services/    workflow, scope, usage, grounding, retrieval, drafts, handoff
app/data/        synthetic local demo fixture
tests/           deterministic API and service regression tests
evaluations/     60 cases, runner, fixtures, generated reports
docs/            scope, architecture, contract, security, tests, next phases
```

See [`docs/DEMO2_SCOPE.md`](docs/DEMO2_SCOPE.md),
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/API_CONTRACT.md`](docs/API_CONTRACT.md),
[`docs/WEB_INTEGRATION.md`](docs/WEB_INTEGRATION.md), and
[`docs/LOCAL_LLM.md`](docs/LOCAL_LLM.md) before integration work.

Demo 1 evidence remains frozen in
[`docs/DEMO_1_COMPLETION_EVIDENCE.md`](docs/DEMO_1_COMPLETION_EVIDENCE.md).
Demo 2 evidence is recorded in
[`docs/DEMO2_COMPLETION_EVIDENCE.md`](docs/DEMO2_COMPLETION_EVIDENCE.md).
