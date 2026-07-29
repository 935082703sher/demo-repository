# RTMC AI Assistant — Demo 1 Completion Evidence

**Evidence date:** 29 July 2026
**Release:** `0.1.0`
**Repository:** `rtmc-ai-assistant`
**Status:** Demo 1 complete; controlled local technical foundation only

## 1. Completion statement

Demo 1 demonstrates a typed FastAPI backend for controlled multilingual RTMC guidance
and complaint-draft preparation. It implements deterministic safety, category,
knowledge-grounding, complaint-review, consent, and duplicate-submit controls.

The demo cannot connect to an official appeal system, officially register an appeal,
generate a case number, or track official status.

## 2. Acceptance evidence

| Requirement | Implementation evidence | Test evidence |
|---|---|---|
| Receive a JSON chat request | `POST /api/v1/chat`; `ChatRequest` Pydantic model | Valid, malformed, empty, and oversized request tests |
| Validate with Pydantic | Strict models reject undeclared fields and invalid values | Invalid-language and request-validation tests |
| Support `uz`, `ru`, and `en` | `Language` enum and localized workflow messages | Three-language response tests |
| Identify six categories | Deterministic `RequestClassifier` | Parameterized tests for all six categories |
| Search only local approved/demo records | `KnowledgeService`; `approved_faq.demo.json` | Active, inactive, expired, language, category, and relevance tests |
| Refuse unsupported factual answers | No approved source produces a human-review result | Unsupported IMEI fee question test |
| Ask structured follow-up questions | Category-specific required fields and localized questions | Network-quality follow-up tests |
| Prepare an in-memory complaint draft | `ComplaintDraftService.upsert` | Draft creation and missing-field tests |
| Show the complete draft | `ComplaintDraftReview` includes all fields, subject, description, version, hash, and notice | Draft-review response tests |
| Require explicit Submit | `SubmitRequest.consent`; backend authorization checks | Submit-without-consent rejection test |
| Never submit to an official system | Submit service contains no official API client | Safe-submit invariant tests |
| Identify human-review cases | Structured escalation reasons and localized responses | Injection, credentials, emergency, threat, legal dispute, misconduct, unclear, no-source, and provider-failure tests |
| Return consistent typed JSON | Closed enums and Pydantic response models | API response assertions and OpenAPI generation tests |
| Automated tests | Pytest suite under `tests/` | **52 passed** |
| Run locally and in Docker | Uvicorn, Dockerfile, Compose, Makefile | Local HTTP smoke test and healthy container smoke test |

## 3. Quality-check results

The final source state produced:

```text
Ruff format --check: 34 files already formatted
Ruff lint:           All checks passed
MyPy strict:         Success; no issues in 34 source files
Pytest:              52 passed in 0.15s
Application import:  Passed
JSON fixture syntax: Passed
Compose YAML syntax: Passed
```

Commands:

```bash
make format-check
make lint
make typecheck
make test
```

## 4. Local API smoke-test evidence

### Health

Request:

```http
GET /health
```

Observed response:

```json
{
  "status": "ok",
  "service": "rtmc-ai-assistant",
  "version": "0.1.0"
}
```

### Controlled chat

Request:

```json
{
  "language": "uz",
  "message": "Mening hududimda mobil internet juda sekin"
}
```

Observed result:

```json
{
  "language": "uz",
  "state": "follow_up",
  "response_type": "follow_up",
  "category": "network_quality",
  "grounded": false,
  "fields_missing": [
    "operator",
    "service_type",
    "region",
    "district",
    "approximate_location",
    "event_time",
    "frequency",
    "duration",
    "impact"
  ],
  "submission_allowed": false,
  "requires_human": false
}
```

The full response also contained generated request/session UUIDs, the required AI
disclosure, and the localized question asking which mobile operator the citizen uses.

### API documentation

- `/openapi.json` returned the `RTMC AI Assistant Demo 1` specification.
- `/docs` returned the Swagger UI successfully.

## 5. Docker evidence

Image built successfully:

```text
rtmc-ai-assistant:demo1
```

The live container inspection returned:

```text
running healthy app
```

This confirms:

- container state: `running`;
- health-check state: `healthy`;
- runtime user: non-root `app`.

The container returned successful `/health` and `/api/v1/chat` responses. The temporary
smoke-test container was stopped and automatically removed after validation.

## 6. Safety evidence

Automated tests confirm:

- prompt-injection attempts do not reveal hidden instructions;
- credentials and sensitive values are not echoed;
- emergencies, threats, self-harm indicators, serious cybersecurity incidents, legal
  interpretation, official-decision disputes, and misconduct allegations stop ordinary
  AI handling;
- unrelated general-knowledge requests are refused;
- expired, inactive, or unapproved knowledge is not used;
- provider failures and unsafe provider output fail safely;
- full IMEI and unsupported draft fields are not accepted;
- draft edits create a new version and hash;
- stale draft versions cannot be submitted;
- consent is bound to the current draft version and privacy-notice version;
- repeated identical Submit events are idempotent;
- a different idempotency key for an already-recorded version is rejected;
- Demo Submit always returns `officially_registered: false`;
- Demo Submit always returns `case_number: null`.

## 7. Safe Submit evidence

For a complete current draft with explicit consent, the observed semantic result is:

```json
{
  "success": false,
  "status": "official_integration_not_configured",
  "officially_registered": false,
  "case_number": null,
  "idempotent_replay": false
}
```

There is no official appeal client, production credential, official database connection,
or case-number generator in the application.

## 8. Delivered artifacts

- application source under `app/`;
- deterministic synthetic fixture under `app/data/`;
- 52-test regression suite under `tests/`;
- `Dockerfile`, `compose.yaml`, and `Makefile`;
- durable repository instructions in `AGENTS.md`;
- scope, architecture, API, security, testing, next-phase, and completion-evidence
  documentation under `docs/`.

## 9. Limitations and approval boundary

This evidence supports completion of **Demo 1 only**. It does not demonstrate production
readiness or approval for citizen use.

Before another phase, RTMC must supply or approve:

- multilingual official knowledge records;
- privacy and consent wording;
- LLM/provider and data-governance decision;
- Nuxt/backend authentication and integration contract;
- persistent database and retrieval design;
- staffed human-handoff and emergency workflow;
- official appeal API contract;
- rate limiting, monitoring, audit storage, backups, security testing, staging, and
  production authorization.
