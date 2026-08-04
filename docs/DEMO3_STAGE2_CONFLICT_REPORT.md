# Demo 3 Stage 2 Conflict Report

## Status

Stage 2 stopped on 2026-08-04 under the approved material-conflict stopping rule.
No Uzbek candidate, Russian translation, or English translation was created. No real
record is approved, active, or runtime-eligible.

## Source integrity and local inspection

The only content source inspected was `DEPT-FAQ-001`. Its SHA-256 matched the approved
expected value:

```text
23f12211e8fbbfd18062e1ef551ecad8b6cad9ab9e5dd5049a181729524225d4
```

The DOCX passed the local package checks: no macro-enabled content type, embedded/OLE
part, executable part, unsafe external relationship, path traversal, or malformed XML
was found. Extraction remained in memory and produced 143 normalized paragraph
references. The PII scan reported no findings. Raw extracted text was not written to
the repository.

## Unresolved material conflict

Conflict ID: `D3S2-CONFLICT-IMEI-DEADLINE-001`

- Provisional candidate: `IMEI-UZ-REGISTRATION-DEADLINE-001`
- Departmental reference: paragraphs 21–22
- Departmental summary: residents are assigned 30 calendar days and nonresidents 60
  calendar days after SIM-slot activation.
- Current official source: <https://uzimei.uz/tariffs>
- Official-source summary: the current tariff page groups resident and nonresident
  individuals together, with one price for registration within 30 calendar days and
  another after 30 days from the first network event.
- Conflict type: registration-period and tariff boundary
- Severity: critical
- Status: unresolved
- Runtime effect: generation, approval, and activation are blocked.

## Required resolution

The RTMC IMEI content owner and an authorized legal reviewer must confirm the current
nonresident registration rule against the governing regulation and operational policy,
then approve exact citizen-facing wording. No engineer or language model may choose
between these sources.

After a documented resolution, Stage 2 must restart source comparison from the clean
Stage 0–1 checkpoint and verify every other candidate independently. Tariffs, payment
methods, registration channels, operator names, identity requirements, legal
references, addresses, and support details remain unverified and must not be inferred
from this partial review.
