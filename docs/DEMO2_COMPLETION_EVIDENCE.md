# RTMC AI Assistant — Demo 2 Completion Evidence

**Recorded:** 2026-07-30  
**Version:** `0.2.0`  
**Branch:** `demo2-grounded-llm`  
**Frozen base:** `v0.1.0-demo1` at
`32b7b0e96260b1d7aa85cbbb5f1ad6bc19e4769b`

## Executive completion statement

Demo 2 is complete as a controlled internal demonstration. It adds deterministic
multilingual scope refusal, server-owned LLM and request limits, approved-knowledge
validation, a configurable real-provider boundary, structured grounded generation,
citation authorization, provider measurements, and a repeatable 60-case multilingual
evaluation.

It is not production-ready and must not be exposed to citizens. No official appeal
system, production RTMC database, production credential, or real citizen data is
present.

## Implemented architecture

- `ScopeService` rejects clear unrelated topics before provider generation.
- `UsageLimitService` atomically authorizes logical LLM requests.
- `RequestRateLimitService` independently protects chat request rate.
- Replaceable repository protocols isolate process-local implementations.
- `KnowledgeService` validates approval, activity, validity, source, language,
  category, synthetic marking, and content hash before retrieval.
- `GroundedGenerationService` enforces timeout and bounded retries while measuring
  attempts, logical results, tokens, estimated cost, and latency.
- `GroundingValidator` accepts only citations that were supplied in retrieved context.
- `LLMProvider` remains vendor-independent. Mock is the default.
- The concrete OpenAI Responses adapter is disabled unless explicitly selected and
  configured; no test or verification made a paid provider call.
- Complaint drafts, consent, versioning, idempotency, and the safe Demo Submit stub
  remain deterministic and independent of the LLM quota.

## Exact limit semantics

Defaults:

```text
LLM_GENERATION_LIMIT_PER_SESSION=10
LLM_QUOTA_WINDOW_SECONDS=86400
REQUEST_RATE_LIMIT_PER_MINUTE=20
```

One logical quota unit is consumed only after safety, language, scope, category,
complaint-follow-up, and approved-knowledge checks establish that generation is
required. Provider retries remain one logical unit but each attempt is counted.

Language selection, clear refusal, validation, deterministic follow-up, missing-source
handoff, human handoff, draft create/review/edit/cancel, consent, and Demo Submit do
not consume LLM quota.

Rate limiting is a separate per-session sliding-minute control. Rejection returns HTTP
429 with `Retry-After` and does not call the provider.

## Scope and localization

Clear travel, religion, unrelated politics, entertainment, homework, recipe, general
medical/legal, coding, weather, and general-knowledge requests are rejected before
generation. The response contains only the active Uzbek, Russian, or English message.
Uncertain RTMC matters receive one clarification and then human handoff.

An explicit `language` value changes the session language. Foreign acronyms or words
do not change it implicitly.

## Approved knowledge and provider behavior

No official RTMC FAQ corpus was supplied. All committed answer fixtures remain visibly
synthetic and `demo_only`.

Production-approved records require:

- active approved status;
- approver identity and approval timestamp;
- validity start and optional expiry;
- HTTPS source;
- exact SHA-256 content hash;
- supported language/category;
- `synthetic=false`.

The provider receives only the retrieved minimum context and server-owned source IDs.
Missing, malformed, expired, inactive, unapproved, wrong-language, or insufficiently
sourced records cannot support an answer. Missing or fabricated provider citations are
rejected.

## Automated quality evidence

Observed final commands and results:

```text
make format-check
56 files already formatted

make lint
All checks passed!

make typecheck
Success: no issues found in 56 source files

make test
95 passed in 0.37s

python -c "from app.main import app; app.openapi()"
application import: ok
OpenAPI version: 0.2.0
```

The suite exercises FastAPI endpoints, complaint state/version/consent/idempotency,
provider outage/authentication/timeout/malformed output, retries, quotas, rate limits,
grounding, fabricated citations, multilingual behavior, and the official-registration
invariants. Tests use no external provider.

## Evaluation evidence

`python -m evaluations.run` observed:

| Language | Passed | Total |
|---|---:|---:|
| Uzbek | 20 | 20 |
| Russian | 20 | 20 |
| English | 20 | 20 |

Measured results:

- category accuracy: 100%;
- language correctness: 100%;
- out-of-scope refusal accuracy: 100%;
- grounded-answer rate: 100%;
- citation validity: 100%;
- unsupported-question refusal rate: 100%;
- human-handoff correctness: 100%;
- critical hallucination count: 0;
- provider attempts: 20;
- reported input tokens: 216;
- reported output tokens: 108;
- configured synthetic estimated cost: `0.000864`;
- average local TestClient latency: 1.223 ms;
- P95 local TestClient latency: 1.714 ms.

Token, cost, and latency values prove measurement wiring only. They are synthetic local
observations, not production forecasts.

Machine and human reports:

- `evaluations/reports/demo2_report.json`;
- `evaluations/reports/demo2_report.md`.

## Local and Docker smoke evidence

Final local health:

```json
{"status":"ok","service":"rtmc-ai-assistant","version":"0.2.0"}
```

Observed Docker sequence:

```text
docker compose config
configuration valid

docker compose build
rtmc-ai-assistant:latest built
package wheel: rtmc_ai_assistant-0.2.0

docker compose up -d
rtmc-api started

curl http://127.0.0.1:8000/health
{"status":"ok","service":"rtmc-ai-assistant","version":"0.2.0"}

POST /api/v1/chat (Uzbek synthetic IMEI fixture)
HTTP 200, language=uz, grounded=true,
source=DEMO-UZ-IMEI-001,
officially_registered=false, case_number=null

docker compose down
container and network removed
```

The redundant source bind mount was removed from Compose because a colon in the local
workspace path made the volume specification invalid. The image already contains the
application source, so this also makes documented rebuilds more portable.

## Security and privacy evidence

- `.env` is ignored and no `.env` file is present.
- `.env.example` contains empty secret placeholders only.
- API keys are environment-backed `SecretStr` values and are not logged or returned.
- Repository scans found no private-key block, OpenAI-style key, GitHub token, AWS key,
  or non-empty committed credential assignment.
- Provider tests use `httpx.MockTransport`; no paid network call occurs.
- Logs omit message and complaint content by default.
- Evaluation and test data are explicitly synthetic.
- Common email and long-number patterns are removed before a factual question reaches
  the configured external adapter.
- Technical usage logs/state are not presented as a production audit system.

## Remaining limitations and RTMC approvals required

- Approved multilingual RTMC knowledge is still required.
- Provider/vendor/model, contract, data-transfer, retention, and budget approval is
  still required.
- Support phone, contact URL, emergency route, and final citizen wording require
  authorized content-owner approval.
- In-memory sessions, limits, drafts, and usage reset on restart and are not shared by
  multiple workers.
- Authentication, centralized limits, persistent audit, staffed handoff, production
  monitoring, kill switch, security testing, and legal/privacy approval remain required.
- Nuxt integration and official appeal API contracts remain unspecified.

## Official-registration confirmation

Demo 2 preserves the backend-enforced result:

```json
{
  "officially_registered": false,
  "case_number": null
}
```

No code path contacts an official appeal system or creates an official case number.
