# Demo 3 Stage 3A Scope

## Purpose

Stage 3A defines internal, governed complaint-workflow contracts before any public API,
website, persistence, secure-storage, operator, or official-system integration. It is an
engineering design checkpoint, not approval of a legal workflow or citizen-facing text.

The branch starts from Stage 2 checkpoint
`5c948668f487c1c62292d09876ff8d9256f7daff`.

## Included

- closed applicant-type, appeal-kind, service-category, and subcategory concepts;
- provisional versioned requirements profiles;
- minimum non-sensitive draft fields and opaque secure-value references;
- deterministic versioning and canonical draft hashing;
- explicit workflow states, transitions, consent binding, and typed errors;
- deterministic human-handoff and anti-invention contracts;
- stable multilingual message keys with synthetic test wording;
- synthetic tests and design documentation.

## Excluded

Stage 3A does not activate knowledge, ingest confidential appeals, accept real PII,
create production storage, add public endpoints, change Nuxt, connect an operator queue,
contact an official appeal system, register a complaint, create a case number, claim a
status, call a real language provider, add PostgreSQL/Redis/migrations, deploy, or start
Stage 3B.

## Compatibility boundary

The existing `/api/v1` schemas, routes, `ComplaintDraftService`, Demo Submit stub, and
OpenAPI surface remain unchanged. The Stage 3A modules are internal and are not wired
into `app.main` or any route. Existing Demo 1, Demo 2, and Stage 0–2 behavior remains the
compatibility baseline.
