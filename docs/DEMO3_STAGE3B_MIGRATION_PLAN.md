# Demo 3 Stage 3B Migration Plan

## Current checkpoint

The adapter is disabled by default. Demo 2 API behavior is the rollback path: disabling the server flag delegates every draft operation to the existing in-memory service and does not create governed state.

Local synthetic evaluation may set:

```text
GOVERNED_COMPLAINT_WORKFLOW_ENABLED=true
```

Enablement fails closed outside `local`, `local-docker`, `test`, or `testing`, and fails when the configured provider is not `mock`. The flag is not accepted from an API request and is absent from OpenAPI.

## Future gates—not authorized in Stage 3B

1. Obtain individually scoped, signed approval evidence for each requirements profile and each language-specific wording version.
2. Resolve legal classification, required-field, retention, consent, accessibility, and operator-ownership questions without changing this checkpoint retroactively.
3. Design and review authenticated secure storage; do not adapt the synthetic issuer into production.
4. Design durable storage and concurrency semantics separately. PostgreSQL and Redis are not present here.
5. Independently approve and activate links/content; content approval must not automatically enable runtime use.
6. Obtain explicit authorization before any official appeal integration and verify that case/status claims originate only from that authenticated system.
7. Re-run privacy, security, API, migration, and rollback acceptance suites before any broader rollout.

No Stage 3C action is implied by this document.
