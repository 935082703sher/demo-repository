# Architecture

## Request flow

```text
RTMC Nuxt backend/API proxy (future)
  -> FastAPI/Pydantic boundary
  -> input guardrails
  -> deterministic language/category workflow
  -> complaint follow-up OR approved/demo-only knowledge search
  -> provider protocol with restricted passages
  -> deterministic output validation
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
- `Guardrails` blocks obvious secrets, injection, high-risk content, unrelated requests,
  and prohibited provider claims. These rules reduce risk; they are not complete
  detection.
- `KnowledgeService` filters by language, category, status, expiry, and relevance.
  It requires at least two fixture keywords so a category word alone cannot be treated as
  evidence for a fee, deadline, contact, procedure, or status.
- `LLMProvider` is a narrow asynchronous protocol. Demo 1 uses `MockLLMProvider`, which
  returns a supplied passage and makes no network call.
- `ComplaintDraftService` isolates thread-safe in-memory drafts, versions, hashes,
  consent records, and duplicate-submit state.

## Storage boundary

The service never connects to the RTMC website database or an official appeal database.
Its stores are dictionaries protected by a lock and are deliberately destroyed at
process restart. This is acceptable only for the local demo.

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
