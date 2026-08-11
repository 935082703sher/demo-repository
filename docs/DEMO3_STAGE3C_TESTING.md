# Demo 3 Stage 3C Testing

## Coverage

The automated suite covers:

- the complete allowed state matrix and its prohibited complement;
- collecting, clarification, recollection, review, acknowledgement, consent, blocking, human-review cancellation, and ordinary cancellation;
- natural person, legal entity, authorized representative, and unknown applicant behavior;
- application, proposal, and complaint independence;
- all six existing public categories and compatible internal subcategories;
- secure-reference-only protected fields and masked review output;
- deterministic hashes, exact session/version/hash consent binding, stale review rejection, and consent invalidation after edits;
- versioned localized single-question follow-ups without residential-address collection;
- every required safety/authority/handoff family, with no configured queue or official claims;
- religion versus region, session/draft continuity, rate limiting, and zero quota/provider use for deterministic refusals;
- no invented or inactive URLs, quarantined knowledge exclusion, and all 138 Stage 2 FAQ-language records remaining unavailable;
- disabled-flag legacy behavior, identical OpenAPI, five unchanged paths, no official submission, and no case/status values;
- all twelve local synthetic scenarios and report privacy.

## Acceptance commands

```text
make format-check
make lint
make typecheck
make test
make pii-check
python -m evaluations.run
python -m evaluations.run_stage3c_scenarios
python -c "from app.main import app; print(app.openapi()['info']['version'])"
docker compose config
```

Additional repository scans check secrets, raw/confidential paths, quarantine state, provider boundaries, submission authority, Git exclusions, and the canonical OpenAPI hash.
