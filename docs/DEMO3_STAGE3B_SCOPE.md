# Demo 3 Stage 3B Scope

## Outcome

Stage 3B adds an internal, server-controlled migration boundary between the existing Demo 2 chat/draft contracts and the provisional Stage 3A complaint workflow. It does not activate production behavior.

## Included

- A backward-compatible adapter for `ComplaintDraftService` operations and `ComplaintDraftReview` output.
- Governed applicant, appeal, category/subcategory, requirements-profile, secure-reference, consent, state-machine, authority-policy, and human-handoff contracts.
- A default-disabled `GOVERNED_COMPLAINT_WORKFLOW_ENABLED` server flag restricted to local/test environments and the mock provider.
- Strict approval-evidence validation with activation kept independently inactive.
- A server-owned registry containing 13 reviewed URLs, all pending, inactive, runtime-ineligible, and test-only.
- Deterministic religion/region handling, privacy enforcement, and acceptance tests.

## Excluded

No public endpoint or schema was added. Stage 3B has no PostgreSQL, Redis, production secure storage, real LLM call, active FAQ content, official appeal connection, Nuxt change, official case number, official status, routing result, legal decision, deadline guarantee, department assignment, push, or release tag.

No approval documents were supplied for this stage. Therefore no approval decision was imported or inferred.

Work stops before Stage 3C and Stage 4.
