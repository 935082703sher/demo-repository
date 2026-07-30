# RTMC AI Assistant — Demo 2 Scope

## Status and baseline

Demo 2 is a controlled internal demonstration. It is not production-ready and must
not be exposed to citizens.

Development starts from the frozen Demo 1 baseline:

- commit: `32b7b0e96260b1d7aa85cbbb5f1ad6bc19e4769b`;
- annotated tag: `v0.1.0-demo1`;
- development branch: `demo2-grounded-llm`.

The Demo 1 tag is immutable. Demo 2 work must remain on its dedicated branch.

## Objective

Extend Demo 1 with source-grounded multilingual generation, a configurable provider
boundary, deterministic scope controls, server-owned usage protections, provider
measurements, and a repeatable multilingual evaluation suite while preserving every
Demo 1 safety invariant.

## Initial repository assessment

The inspected Demo 1 implementation contains:

- FastAPI routes for health, chat, complaint drafts, draft review/cancellation, and
  the safe Demo Submit stub;
- strict Pydantic request, response, domain, knowledge, and consent models;
- deterministic multilingual category classification and guardrails;
- process-local conversation clarification state and complaint-draft state;
- deterministic retrieval from explicitly synthetic multilingual fixtures;
- a provider-independent `LLMProvider` protocol and network-free mock provider;
- consent, draft-version, and idempotency enforcement;
- 52 deterministic tests, including API, draft-state, provider-failure, grounding,
  guardrail, and safe-submission behavior.

The application version remains `0.1.0` until every Demo 2 acceptance criterion
passes.

## Included features

Demo 2 includes:

- deterministic out-of-scope classification before provider generation;
- one-language-only Uzbek, Russian, and English citizen messages;
- a replaceable, process-local LLM quota repository;
- a separate replaceable, process-local request-rate repository;
- typed quota and rate-limit responses;
- safe rendering of approved contact configuration without invented values;
- approved-knowledge metadata validation and a documented import procedure;
- minimum-context retrieval and machine-readable citations;
- a provider-independent grounded-generation contract;
- the deterministic mock provider as the default;
- one configurable real-provider adapter that remains disabled without explicit
  configuration and authorization;
- structured provider-output validation, citation verification, timeouts, and bounded
  retries;
- logical-request and provider-attempt measurements, token counts, estimated cost, and
  latency;
- safe degradation for missing knowledge, invalid configuration, provider failures,
  and malformed or unsafe output;
- a synthetic 60-case evaluation set covering Uzbek, Russian, and English;
- machine-readable and human-readable evaluation evidence.

## Explicitly excluded

Demo 2 does not:

- connect to an official appeal system or production RTMC database;
- register, update, route, or track an official appeal;
- generate a case number, department, deadline, status, or official decision;
- activate a paid provider or make paid calls during automated tests;
- collect real citizen complaints or use real personal data;
- add a production frontend, PostgreSQL, Redis, Kubernetes, or production deployment;
- invent RTMC regulations, contacts, fees, deadlines, procedures, or legal conclusions.

## Assumptions and approval dependencies

- No approved RTMC knowledge corpus has been supplied. Schema, validation, import,
  and unmistakably synthetic fixtures will be implemented without official answers.
- No provider choice has been formally approved. A configuration-selected adapter
  may be implemented, but mock remains the default and no real call is authorized.
- No approved support phone or contact URL has been supplied. Missing values produce
  neutral human-handoff wording.
- Privacy wording, retention, production audit requirements, and provider data
  processing remain RTMC organizational decisions.
- Demo 2 uses one process. In-memory state is neither shared across workers nor
  retained after restart.

## Safety boundaries

The backend remains authoritative for scope, quota, request rate, source approval,
citations, complaint state, consent, and submission authorization. Provider text is
untrusted and cannot change those decisions.

Every Demo Submit result must preserve:

```json
{
  "officially_registered": false,
  "case_number": null
}
```

No citizen-facing factual answer may be returned unless an active, approved,
non-expired, language-matching source supports it. Synthetic demo fixtures must be
identified as synthetic and must never be interpreted as production-approved facts.

## Definition of Done

Demo 2 is complete only when:

- all Demo 1 tests and all new Demo 2 tests pass;
- formatting, linting, strict type checking, import, and OpenAPI generation pass;
- local and Docker health/chat smoke tests pass;
- deterministic scope refusals are localized and do not call or consume provider quota;
- quotas work at configured limits of 5 and 10, with provider attempts measured
  separately from logical allowance;
- deterministic complaint operations remain available after quota exhaustion;
- request-rate protection returns retry information without calling the provider;
- approved-knowledge validation excludes malformed, unapproved, inactive, expired,
  wrong-language, or insufficiently sourced records;
- grounded outputs cite only records supplied to the provider;
- missing sources and provider/configuration failures fail safely;
- the 60-case evaluation reports zero critical hallucinations;
- no secret, real citizen data, official integration, or invented contact is present;
- version `0.2.0` is set only after all preceding conditions pass.

## Known limitations

- Process-local counters and sessions reset on restart and are bypassable with a new
  session.
- Multiple application workers do not share counters, sessions, or drafts.
- Synthetic fixtures demonstrate mechanics, not official RTMC knowledge.
- Deterministic scope and category rules reduce risk but do not claim perfect natural
  language understanding.
- Cost is an estimate and is reported only when configured pricing and provider token
  counts are available.
- Logs are technical demo events, not a production audit system.
- A configured real-provider adapter is not evidence of RTMC approval to send data or
  incur cost.
