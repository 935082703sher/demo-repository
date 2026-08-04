# Testing

The suite is deterministic, uses synthetic data, and makes no external or paid API calls.

```bash
make format
make lint
make typecheck
make test
make pii-check
make check
python -m evaluations.run
```

Equivalent commands:

```bash
ruff format app tests evaluations
ruff check app tests evaluations
mypy app tests evaluations
pytest
```

Coverage includes:

- health and OpenAPI startup;
- request validation, malformed JSON, and message limits;
- six categories across Uzbek, Russian, and English;
- missing-language selection and unclear-after-one-clarification escalation;
- unsupported facts, unrelated scope, explicit synthetic grounding, and source metadata;
- inactive, expired, and nominally approved-but-undated knowledge rejection;
- approval identity/source/hash validation and validation-only import reporting;
- exact localized scope, quota, and rate-limit responses;
- limits of 5 and 10, session isolation, reset, browser-counter distrust, retry attempts,
  and continued deterministic complaint behavior after quota exhaustion;
- structured configured-provider output, authentication, malformed output, timeout,
  bounded retries, token/cost/latency accounting, and no paid calls;
- missing and fabricated citation rejection;
- injection, credentials, emergency, threat, provider outage, and unsafe provider output;
- draft field allowlists, missing fields, version/hash changes, stale edits, retrieval,
  cancellation, and unknown drafts;
- explicit consent, exact notice/version binding, incomplete/stale rejection,
  idempotent replay, duplicate-key conflict, and the absence of official case numbers.
- strict source manifests and safe content-free SHA-256 verification;
- archive traversal, symlink, executable, macro, nesting, type, size, and compression limits;
- offline-only extraction policy and safe synthetic ZIP extraction;
- defined PII patterns, nested derived-fixture rejection, and provider-request redaction;
- separate source/record approval and activation, conflicts, language, review, validity,
  and content-hash enforcement.

New defects should receive a focused regression test at the lowest meaningful layer. API
tests should assert both HTTP status and stable public error code. Never add fixtures
containing real citizens, credentials, official-looking case numbers, or invented RTMC
facts.

Known limitations: keyword classifiers and guardrails are not semantic safety models;
concurrency is tested through locking semantics rather than load tests; Docker smoke
testing requires a local Docker engine.
