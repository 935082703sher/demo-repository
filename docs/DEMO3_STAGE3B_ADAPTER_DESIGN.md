# Demo 3 Stage 3B Adapter Design

## Canonical ownership

The adapter selects one source of workflow truth:

- Flag disabled: the existing `ComplaintDraftService` remains canonical and the adapter delegates without creating governed state.
- Flag enabled: one internal canonical adapter record owns the governed draft and the exact legacy projection fields. The legacy service is not written. `ComplaintDraftReview` is derived from that record.

This prevents parallel legacy and governed workflow stores from drifting.

## Explicit mapping

| Legacy input/output | Governed representation |
| --- | --- |
| `session_id`, language, category | Same typed values |
| Legacy `fields` | Safe occurrence details; `subject` and `description` map to dedicated governed fields |
| `version` | Same governed draft version |
| `draft_hash` | Governed canonical hash |
| Missing legacy fields | Versioned synthetic profile requirements |
| `personal_data_to_submit` | Secure field-type names only; never raw values or opaque IDs |
| Legacy escalation reason | Typed handoff reason plus the original stable reason code in a safe internal summary |
| Submit consent | Consent binding for exact draft ID, version, hash, language, privacy notice, wording version, and timestamp |
| Submit result | Existing non-official result with `officially_registered=false` and `case_number=null` |

Applicant type, appeal kind, and subcategory are independent. Public legacy requests do not contain those values, so the enabled adapter does not infer them: it returns clarification requirements. Internal local/test callers may provide an explicit `GovernedMappingContext`. Lossy identity, category, language, session, or stale-version mappings are rejected.

## Deterministic flow

Existing chat orchestration retains language selection, guardrails, scope classification, category classification, and current-request refusal. When enabled, typed human-handoff projections are observed internally. The adapter then uses explicit classifications to select a pending synthetic requirements profile, compute missing fields, reject raw PII, accept only opaque references from the non-retaining synthetic issuer, create/edit the governed draft, derive a legacy review, bind consent, and stop at `submission_blocked`.

Every material edit increments the version, changes the canonical hash where semantic content changes, and invalidates consent. Stale versions cannot advance.

## Authority boundary

Protected claims continue through the Stage 3A authority policy. The adapter has no code path for official registration, status lookup, case numbering, routing, legal interpretation, deadline guarantees, or department assignment. Human handoff always has `queue_status=not_configured`.
