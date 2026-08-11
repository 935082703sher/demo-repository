# Demo 3 Stage 3A State Machine

## States

`collecting`, `clarification_required`, `human_review_required`, `review_ready`,
`awaiting_consent`, `consent_recorded`, `submission_blocked`, and `cancelled` are the
only states. None implies registration, acceptance, assignment, processing, resolution,
or any other official action.

## Allowed transitions

| From | Allowed targets |
| --- | --- |
| `collecting` | `clarification_required`, `human_review_required`, `review_ready`, `cancelled` |
| `clarification_required` | `collecting`, `human_review_required`, `review_ready`, `cancelled` |
| `human_review_required` | `cancelled` |
| `review_ready` | `awaiting_consent`, `human_review_required`, `cancelled` |
| `awaiting_consent` | `consent_recorded`, `human_review_required`, `cancelled` |
| `consent_recorded` | `submission_blocked`, `cancelled` |
| `submission_blocked` | `cancelled` |
| `cancelled` | none |

The transition table is centralized in `ALLOWED_WORKFLOW_TRANSITIONS`.

## Guards

- missing requirements prevent `review_ready`;
- unknown applicant/appeal/subcategory requires clarification;
- a clarified classification is recorded through a new version and hash;
- a human-review reason prevents automatic progression;
- direct transition to `consent_recorded` is forbidden;
- consent must match the current draft ID, version, hash, notice version, and language;
- edits increment the version, change the hash, and invalidate recorded consent;
- edits use the dedicated versioned edit operation rather than a generic state edge;
- cancelled drafts cannot be edited, consented, or submitted;
- the only Stage 3A post-consent outcome is `submission_blocked`.

Failures use `WorkflowErrorCode` and `ComplaintWorkflowError`. Error strings contain a
stable code only and never echo draft text or secure values.
