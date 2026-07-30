# Architecture

## Request flow

```text
RTMC Nuxt backend/API proxy (future)
  -> FastAPI/Pydantic boundary
  -> input guardrails
  -> active language + per-session request-rate decision
  -> deterministic scope and category workflow
  -> complaint follow-up OR approved/demo-only knowledge search
  -> atomic logical-generation quota
  -> configured provider protocol with restricted passages
  -> bounded attempts + token/cost/latency measurement
  -> deterministic citation and output validation
  -> typed answer/refusal/handoff JSON
```

The language provider can suggest wording only. It cannot change conversation state,
authorize submission, search arbitrary sources, call tools, or create official facts.

## Components

- `app.main` constructs isolated application state, middleware, and safe exception handlers.
- `api.routes` validates API models and delegates to services.
- `AssistantService` owns state transitions for Demo chat interactions.
- `RequestClassifier` uses reviewable multilingual keyword rules. Its confidence is a
  rule score and is not presented as calibrated ML confidence.
- `Guardrails` blocks obvious secrets, injection, high-risk content, and prohibited
  provider claims. `ScopeService` rejects clear unrelated requests before generation.
  These rules reduce risk; they are not complete detection.
- `KnowledgeService` filters by language, category, approval, source, activity,
  validity, content hash, synthetic marking, and relevance.
  It requires at least two fixture keywords so a category word alone cannot be treated as
  evidence for a fee, deadline, contact, procedure, or status.
- `UsageLimitService` and `RequestRateLimitService` use independent replaceable
  repositories; process-local implementations are lock-protected.
- `LLMProvider` is a narrow asynchronous protocol. Demo 2 defaults to
  `MockLLMProvider`; a configured OpenAI adapter remains unavailable without model and
  environment-backed key.
- `GroundedGenerationService` applies timeout/retry bounds and records attempts,
  logical results, tokens, cost, and latency.
- `GroundingValidator` rejects missing or fabricated citations before any answer.
- `ComplaintDraftService` isolates thread-safe in-memory drafts, versions, hashes,
  consent records, and duplicate-submit state.

## Storage boundary

The service never connects to the RTMC website database or an official appeal database.
Its stores are dictionaries protected by a lock and are deliberately destroyed at
process restart. Multiple workers do not share state. This is acceptable only for the
internal demo.

## Submission invariant

The Submit endpoint has no official backend client. A complete current draft plus
explicit consent creates an in-memory consent record and returns:

```json
{
  "success": false,
  "status": "official_integration_not_configured",
  "officially_registered": false,
  "case_number": null
}
```

This is a structural guarantee, not a prompt instruction.

## Later integration seam

A future approved official client belongs behind a backend-only interface after
authentication, data-field, privacy, audit, idempotency, timeout, retry, and official
response contracts are approved. It must not be added to the language provider.
