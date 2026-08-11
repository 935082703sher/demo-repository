# Demo 3 Stage 2 Completion Evidence

- Recorded: 2026-08-04
- Formal checkpoint review rerun: 2026-08-11
- Branch: `demo3-approved-content-staging`
- Stage 2 checkpoint base: `8a134e9e5f747748f5416b00dbeb3a1c0ef10212`

## Scope completed

Only `MNP va IMEI FAQ.docx` was processed. Its SHA-256 matched the approved value
before local extraction:

```text
23f12211e8fbbfd18062e1ef551ecad8b6cad9ab9e5dd5049a181729524225d4
```

The safe DOCX boundary inspected the package locally and extracted normalized text in
memory. The PII gate ran before any derived candidate artifact entered the repository.
The RAR, confidential appeal documents, and PDFs were not opened or used.

Compound FAQ material was split into atomic records and checked against current
official UZIMEI, MNP, RTMC, Customs, and Lex.uz sources. Silence was recorded as
pending, not as confirmation. Four divergent or insufficiently current source items
were excluded into independent conflict records.

## Review package counts

| Measure | Count |
| --- | ---: |
| Uzbek candidates | 46 |
| Russian translation drafts | 46 |
| English translation drafts | 46 |
| Verified Uzbek candidates | 31 |
| Partially verified Uzbek candidates | 2 |
| Pending-verification Uzbek candidates | 13 |
| Contradicted candidates admitted | 0 |
| Independently quarantined source items | 4 |
| Runtime-eligible records across all languages | 0 |

Category totals are 23 IMEI and 23 MNP Uzbek records. Every candidate and translation
has `approval_status=pending_review`, `activation_status=inactive`,
`runtime_eligible=false`, `quarantined=true`, and blank human decision fields.
Every translation draft links to the exact Uzbek record ID, version, and content hash.

## Conflict isolation

The following items produced no candidate or translation:

- `D3S2-CONFLICT-IMEI-DEADLINE-001`: disputed 30-day/60-day registration wording;
- `D3S2-CONFLICT-IMEI-PAYMENT-METHODS-001`: departmental and current official payment
  method lists differ;
- `D3S2-CONFLICT-IMEI-REGISTRATION-POINTS-001`: exact address/operator list is not
  confirmed by the current dynamic directory;
- `D3S2-CONFLICT-IMEI-CUSTOMS-FREQUENCY-001`: route-specific half-year wording needs a
  current governing act and clause.

The tariff candidates describe current published tariff boundaries only. They
explicitly make no interpretation of the quarantined registration deadline.

## Acceptance evidence

```text
make format-check
70 files already formatted

make lint
All checks passed

make typecheck
Success: no issues found in 70 source files

make test
164 passed

python -m evaluations.run
60 of 60 cases passed; critical hallucinations: 0; synthetic-only: true

DOCX security tests
7 passed

Stage 0-2 governance, confidentiality, PII, and candidate tests
61 passed

Provider and submission-safety tests
15 passed

Candidate package validation
46 Uzbek; 46 Russian; 46 English; runtime eligible: 0

PII scans
Existing fixture gate passed; data/knowledge and reports passed

JSON validation
6 candidate/report JSON files valid

Secret, local-path, and raw-document scans
No findings

OpenAPI generation
Version 0.2.0; 5 paths

docker compose config
Valid; LLM_PROVIDER=mock; LLM_API_KEY empty
```

The evaluation's provider-attempt metric refers only to the deterministic mock. No
real or paid provider call occurred. No source content was sent to an application LLM.

## Boundary confirmation

- No source document, raw extraction, confidential case content, PII, credential, or
  local source manifest is present in Git artifacts.
- Candidate packages are not connected to runtime retrieval.
- No record was approved or activated.
- No official appeal integration, registration event, case number, or official status
  was added.
- No Demo 3 tag was created and no branch was pushed.
- Stage 3 was not started.

Stage 2 engineering preparation is complete for human review, not production use.
Named IMEI/MNP content owners, authorized legal reviewers where identified, and
separate Russian/English reviewers remain mandatory before any later activation work.
