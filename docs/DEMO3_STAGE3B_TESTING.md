# Demo 3 Stage 3B Testing

## Acceptance coverage

Automated tests cover:

- default-disabled, enabled-local, unsafe-environment, real-provider, and unknown-value flag behavior;
- unchanged public schemas and identical enabled/disabled OpenAPI documents;
- explicit and ambiguous adapter mapping, independent applicant/appeal/category values, profile selection, missing-field progression, version and canonical-hash preservation;
- synthetic secure-reference issuance and absence of raw protected values from drafts, responses, errors, and idempotency evidence;
- creation, edit, consent invalidation, stale-version rejection, complete consent binding, idempotency, and terminal `submission_blocked` state;
- lossless legacy escalation mapping and `queue_status=not_configured`;
- protected-claim denial without server-owned authority;
- exact religion/region cases in Uzbek, Russian, and English; mixed case/spelling; province, district, and city text; one clarification for an ambiguous typo; current-request-only refusal; draft/session continuity; and zero provider calls for deterministic refusals;
- 13 pending/inactive links, unknown-link rejection, cross-language rejection, and URL-invention prevention;
- exact approval identity/version/hash/language/lifetime checks, blanket-approval rejection, and independent inactive runtime state;
- all 138 Stage 2 FAQ/translation records remaining unavailable.

## Required commands

```text
make format-check
make lint
make typecheck
make test
make pii-check
python -m evaluations.run
python -c "from app.main import app; print(app.openapi()['info']['version'])"
docker compose config
```

The evaluation fixtures are synthetic. Test output must never print raw sensitive input. The canonical OpenAPI document is compared before and after feature enablement to prove that the flag is server-only.
