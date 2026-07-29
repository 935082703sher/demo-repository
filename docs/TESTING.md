# Testing

The suite is deterministic, uses synthetic data, and makes no external or paid API calls.

```bash
make format
make lint
make typecheck
make test
make check
```

Equivalent commands:

```bash
ruff format app tests
ruff check app tests
mypy app tests
pytest
```

Coverage includes:

- health and OpenAPI startup;
- request validation, malformed JSON, and message limits;
- six categories across Uzbek, Russian, and English;
- missing-language selection and unclear-after-one-clarification escalation;
- unsupported facts, unrelated scope, explicit synthetic grounding, and source metadata;
- inactive, expired, and nominally approved-but-undated knowledge rejection;
- injection, credentials, emergency, threat, provider outage, and unsafe provider output;
- draft field allowlists, missing fields, version/hash changes, stale edits, retrieval,
  cancellation, and unknown drafts;
- explicit consent, exact notice/version binding, incomplete/stale rejection,
  idempotent replay, duplicate-key conflict, and the absence of official case numbers.

New defects should receive a focused regression test at the lowest meaningful layer. API
tests should assert both HTTP status and stable public error code. Never add fixtures
containing real citizens, credentials, official-looking case numbers, or invented RTMC
facts.

Known limitations: keyword classifiers and guardrails are not semantic safety models;
concurrency is tested through locking semantics rather than load tests; Docker smoke
testing requires a local Docker engine.
