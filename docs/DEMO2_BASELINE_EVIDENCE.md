# Demo 2 Baseline Evidence

**Recorded:** 2026-07-30  
**Branch created:** `demo2-grounded-llm`  
**Frozen Demo 1 tag:** `v0.1.0-demo1`

## Git verification

Before Demo 2 application or documentation changes:

```text
git rev-parse HEAD
32b7b0e96260b1d7aa85cbbb5f1ad6bc19e4769b

git rev-list -n 1 v0.1.0-demo1
32b7b0e96260b1d7aa85cbbb5f1ad6bc19e4769b
```

The annotated Demo 1 tag was neither modified nor recreated.

`git status --short` reported one pre-existing worktree difference in
`.dockerignore`: its final newline had been removed. The content was otherwise
unchanged. That difference was preserved rather than discarded.

The configured remote is:

```text
origin  https://github.com/robiyakhmed13-ux/RTMC-AI-chat-bot.git
```

## Demo 1 quality checks

The first attempt showed that the shell did not have the pinned tools on `PATH`.
A temporary Python 3.12 virtual environment was therefore created outside the
repository and the exact `.[dev]` dependencies from `pyproject.toml` were installed.

Observed baseline results:

```text
ruff format --check app tests
34 files already formatted

ruff check app tests
All checks passed!

mypy app tests
Success: no issues found in 34 source files

pytest -q
....................................................                     [100%]
```

The 52 tests include FastAPI endpoint requests, complaint draft creation and
versioning, consent and idempotency, provider outage behavior, unsafe provider output,
knowledge expiry, multilingual responses, and the invariant that Demo Submit never
returns an official case number.

## Inspected Demo 1 surface

- Application version: `0.1.0`.
- Routes: `GET /health`, `POST /api/v1/chat`,
  `POST /api/v1/complaints/draft`, `GET /api/v1/complaints/{draft_id}`,
  `DELETE /api/v1/complaints/{draft_id}`, and
  `POST /api/v1/complaints/{draft_id}/submit`.
- Provider: provider protocol plus deterministic network-free mock.
- Knowledge: process-local JSON fixture retrieval with language, category, status,
  expiry, and approval-date checks.
- Complaint state: process-local, lock-protected drafts, version hashes, consent
  records, and idempotent Demo Submit responses.
- Environment: `RTMC_`-prefixed Pydantic settings and a committed `.env.example`
  containing no credentials.
- Safety invariant: `officially_registered` is always `false` and `case_number` is
  always `null` for Demo Submit.
