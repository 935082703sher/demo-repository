# Demo 3 Stage 3A Domain Design

## Independent classifications

The internal model keeps these dimensions separate:

- applicant type: `natural_person`, `legal_entity`, `authorized_representative`, or
  `unknown`;
- appeal kind: `application`, `proposal`, `complaint`, or `unknown`;
- service category: the existing `imei`, `mnp`, `number_codes`, `network_quality`,
  `website_issue`, or `other` enum;
- subcategory: a closed set reused from Stage 2 where available, plus explicit
  `unknown` and `unsupported` values.

No category determines an appeal kind. An unknown applicant, appeal kind, or
subcategory remains unknown and enters clarification; it is never silently converted.
The English appeal-kind identifiers are technical identifiers. Their Uzbek, Russian,
and English public labels need legal and language-owner approval.

## Requirements profiles

`RequirementsProfile` holds a profile ID/version, effective date, the four independent
classifications, ordinary fields, opaque secure-field types, conditional requirements,
human-review triggers, owner role, and synthetic source references. Stage 3A enforces:

```json
{
  "approval_status": "pending_review",
  "legal_review_status": "pending_review",
  "production_eligible": false,
  "provisional": true
}
```

These profiles support deterministic engineering tests only. They do not assert that
RTMC or Uzbek law requires any field. Natural-person and legal-entity profiles cannot
be mixed.

## Draft and consent

`ComplaintWorkflowDraft` contains internal/session IDs, language, all classification
dimensions, screened subject/description/occurrence details, opaque secure references,
missing keys, human-review state, workflow state, version/hash, timestamps, profile
version, notice version, and local consent state. It has no case number, official
status, department assignment, legal decision, or promised deadline.

`ConsentBinding` binds explicit consent to the exact draft ID, version, hash,
privacy-notice version, language, and timezone-aware timestamp. An edit produces a new
version/hash and invalidates recorded consent.

## Existing models requiring a later migration decision

Stage 3A deliberately does not refactor the public API:

- `ComplaintDraftReview` lacks applicant type, appeal kind, subcategory, secure
  references, requirements profile, and the governed state machine.
- `DraftUpsertRequest.fields` and legacy `REQUIRED_FIELDS` are category-only string
  dictionaries. They must not be treated as approved legal requirements.
- `ConsentRecord` has version/hash/notice binding but lacks language binding.
- legacy `EscalationReason` uses a smaller and differently named public set.
- `ConversationState` is an API conversation state, not the governed complaint state.

Stage 3B must choose an explicit backward-compatible adaptation or API-version strategy
before any migration. These concepts must not be silently replaced.
