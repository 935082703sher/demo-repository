# Demo 3 Stage 3A Data Flow

Stage 3A defines this future-safe sequence without wiring it to an endpoint:

```text
session-controlled language
  -> deterministic applicant / appeal / category / subcategory classification
  -> unknown classification: clarification_required
  -> deterministic safety and handoff checks
  -> human trigger: human_review_required
  -> provisional requirements-profile match
  -> PII screening of ordinary text and field names
  -> sensitive input: future SecureValueIssuer boundary -> opaque reference only
  -> governed draft assembly
  -> canonical serialization -> SHA-256 draft hash
  -> complete draft: review_ready -> awaiting_consent
  -> exact version/hash/notice/language/time consent binding
  -> consent_recorded -> submission_blocked
```

## Trust boundaries

- Citizen text is untrusted and cannot define classifications, profile requirements,
  transitions, approval state, or official facts.
- A language model may not change state or authority context.
- Requirements profiles are provisional and cannot make a legal-requirement claim.
- Approved source IDs and official-integration state are server-owned inputs to the
  anti-invention policy.
- Stage 2 candidate files remain quarantined and are not read by this workflow.
- No provider, database, queue, file store, official API, or network call is present.

## Data minimization

Only screened issue content, structured non-sensitive occurrence details, and opaque
references enter a draft. Hashing includes semantic content, profile/notice versions,
and the draft version, but excludes timestamps and random draft/session IDs so ordering,
whitespace, and restart do not change the hash for equivalent content.
