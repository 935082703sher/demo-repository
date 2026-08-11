# Demo 3 Stage 3A Testing

## Focused contract tests

`tests/test_complaint_workflow_contracts.py` covers classification independence,
profile isolation, unknown classification, provisional state, PII rejection,
completeness, canonical hashing, editing, consent binding, human review, transitions,
cancellation, and the `submission_blocked` terminal outcome.

`tests/test_stage3a_safety_contracts.py` covers opaque UUIDv4 references, closed
serialization, synthetic-only secure issuance, safe string/log representations, handoff
reasons, the unconfigured queue, all protected claims, official-integration-only claims,
message completeness, and session-controlled language.

## Full acceptance

Run:

```bash
make format-check
make lint
make typecheck
make test
python -m evaluations.run
make pii-check
```

Also scan changed files for secrets, raw documents, local paths, and PII; validate Stage
2 quarantine; compare canonical OpenAPI output with the Stage 3A baseline; validate
Docker Compose; import the application; and run the two focused Stage 3A test modules.

All fixtures must be obviously synthetic. Network access and a real provider are not
permitted.
