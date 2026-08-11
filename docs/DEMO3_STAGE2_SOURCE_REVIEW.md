# Demo 3 Stage 2 Source Review

## Scope and method

Only `DEPT-FAQ-001` was processed after its approved SHA-256 was verified. The RAR,
appeal documents, and PDFs were not opened or used. DOCX extraction stayed local and
in memory. Candidate text passed the PII gate before repository files were created.

Compound FAQ answers were split into atomic claims. Each claim was compared with a
current primary source. A source's silence was recorded as `pending`; it was never
treated as confirmation. Materially divergent or unsafe-to-refresh claims were
excluded and recorded in the conflict report.

## Candidate results

- Uzbek candidates: 46
- Verified: 31
- Partially verified: 2
- Pending official verification: 13
- Contradicted candidates admitted to the package: 0
- Independently quarantined source items: 4
- Runtime-eligible records: 0

## Primary sources reviewed

| Source | Relevant use | Retrieved |
| --- | --- | --- |
| <https://lex.uz/docs/-4517458> | Current IMEI regulation context | 2026-08-04 |
| <https://uzimei.uz/> | IMEI identity, applicant, and status information | 2026-08-04 |
| <https://uzimei.uz/?id=instructions> | Registration methods and postal requirements | 2026-08-04 |
| <https://uzimei.uz/tariffs> | Current tariffs and payment-method comparison | 2026-08-04 |
| <https://mnp.uz/> | MNP definition, GSM scope, interval, fee, and process | 2026-08-04 |
| <https://mnp.uz/knowledge> | MNP FAQ coverage and verification gaps | 2026-08-04 |
| <https://rtmc.uz/contact/faq> | RTMC IMEI/MNP FAQ cross-check | 2026-08-04 |
| <https://rtmc.uz/news/-how-to-change-your-operator-while-keeping-your-number> | Current MNP guidance | 2026-08-04 |
| <https://rtmc.uz/news/new-procedure-for-registering-mobile-device-imei-codes> | Current IMEI declaration context | 2026-08-04 |
| <https://uzimei.customs.uz/> | Customs IMEI order status | 2026-08-04 |

`https://rtmc.uz/contact` could not be reliably retrieved during review. No contact
detail was inferred from that failure, and no candidate depends on it.

## Review boundary

All candidates remain proposed wording. `verified` means the cited public source
supports the atomic factual claim; it does not mean RTMC has approved the record.
Named content owners, legal reviewers where required, and language reviewers must
make separate record-level decisions before any later activation workflow.
