# Demo 3 Stage 3B Completion Evidence

## Checkpoint

- Starting accepted Stage 3A commit: `bedaed86ae6d242a83042d5f62af96db21ff180d`
- Working branch: `demo3-complaint-workflow-adapter`
- Scope: Stage 3B only
- Approval documents supplied: none
- Public endpoints added: zero
- Real provider calls introduced: zero
- Official integration introduced: none

## Safety invariants

- The server feature flag defaults to disabled and Demo 2 remains the default behavior.
- Enabled mode is restricted to local/test environments with the mock provider.
- Governed drafts are canonical only in enabled mode; the legacy store is not also written.
- Raw sensitive values are rejected from ordinary drafts and idempotency keys. The synthetic secure issuer retains no value.
- Consent binds draft ID, version, hash, language, privacy-notice version, consent-wording version, and timestamp; material edits invalidate it.
- The final state is `submission_blocked`. Results remain unsuccessful, not officially registered, and without a case number or official status.
- Human handoff has no configured operator queue.
- All links and all 138 FAQ-language records remain unavailable for runtime retrieval.

## Verification results

- Ruff formatting: 83 files formatted; format check passed.
- Ruff lint: passed.
- Mypy strict type check: passed for 83 source files.
- Pytest: 245 passed.
- Privacy scan of `app/data` and `evaluations/cases`: passed with zero failed paths.
- Demo 2 multilingual evaluation: 60/60 passed, 20/20 per language, zero failed cases, zero critical hallucinations, synthetic-only, and zero estimated paid-provider cost.
- Application version: `0.2.0`.
- OpenAPI: unchanged SHA-256 `9e12e7d3663b8827c4166ef3e53a8e45427aca62ddf64a20931a6c8be4654b7c`, with the same five paths.
- Compose configuration: valid; adapter flag resolves to `false` and provider to `mock`.
- Stage 2 FAQ-language records: 138 total, zero runtime-retrievable.
- Link registry: 13 total, zero runtime-eligible.
- `git diff --check`: passed.

The Stage 3B commit SHA is recorded in the final task handoff after the exact required commit is created. No push or tag is performed.

## Unresolved decisions

Named owners/approvers, exact legal requirements by applicant/appeal/subcategory, approved citizen-facing wording, retention/deletion rules, production secure storage, operator queue ownership, durable storage, official integration authorization, and content/link activation all remain unresolved and out of scope.
