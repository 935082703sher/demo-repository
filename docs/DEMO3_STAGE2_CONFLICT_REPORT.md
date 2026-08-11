# Demo 3 Stage 2 Conflict Report

## Status

Stage 2 continued on 2026-08-04 only for source items with no unresolved material
conflict. The resulting Uzbek, Russian, and English records remain pending review,
inactive, quarantined, and unavailable for runtime retrieval.

The disputed IMEI resident/nonresident deadline was not interpreted or resolved. Tariff
records reproduce the current official tariff boundaries but explicitly do not treat
those boundaries as legal registration deadlines.

## Source integrity and local inspection

The only departmental content source processed was `DEPT-FAQ-001`. Its approved
SHA-256 was verified before extraction:

```text
23f12211e8fbbfd18062e1ef551ecad8b6cad9ab9e5dd5049a181729524225d4
```

The DOCX passed the local package checks. Extraction stayed in memory, and normalized
records passed the PII gate before entering Git. No raw extraction, source document,
case file, or personal value was written to the repository.

## Independent quarantines

### `D3S2-CONFLICT-IMEI-DEADLINE-001` — critical

The departmental source's 30-day/60-day registration wording remains unresolved
against the current UZIMEI tariff boundary. Paragraphs 21, 22, 50, and 51 produced no
candidate or translation. The RTMC IMEI content owner and authorized legal reviewer
must complete `DEMO3_STAGE2_CONFLICT_RESOLUTION_REQUEST.md`.

### `D3S2-CONFLICT-IMEI-PAYMENT-METHODS-001` — high

The departmental list contains Upay, while the current official page lists Payme,
Click, Humans, Paynet, and Bank. Paragraphs 25–26 remain excluded. The RTMC IMEI
content owner must approve the complete current list and decide whether to correct the
FAQ.

### `D3S2-CONFLICT-IMEI-REGISTRATION-POINTS-001` — high

The exact address and named-operator list in paragraphs 6, 10, 42, and 44 are not
confirmed by the current dynamic UZIMEI registration-point directory. The RTMC IMEI
content owner must approve a current location source or require use of the dynamic
directory only.

### `D3S2-CONFLICT-IMEI-CUSTOMS-FREQUENCY-001` — high

The route-specific half-year wording in paragraphs 33–34 requires current legal and
customs verification. Current Customs publications describe changed declaration and
allowance procedures but do not confirm that exact rule for every route. The RTMC IMEI
content owner and authorized legal reviewer must identify and approve the current act
and clause.

## Runtime effect

All four source items are absent from candidate and translation packages. Their
conflict records are maintained in `reports/demo3_stage2_conflicts.json`. Missing or
partial answers from RTMC do not resolve a conflict, and no conflict record can become
eligible for activation.
