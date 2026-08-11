# Demo 3 Knowledge Governance

## Trust model

Department-supplied does not mean approved for answering. Source integrity, human
approval, and runtime activation are independent controls. The answer path must fail
closed if any required evidence is missing.

Approval states are:

```text
draft -> pending_review -> approved -> withdrawn
```

Activation states are:

```text
inactive -> active -> inactive/expired/superseded/withdrawn
```

Withdrawn is terminal. Draft content cannot jump directly to approved, and content
cannot become answerable merely because an approval field was populated.

## Source activation

An active source requires all of the following:

- explicit human approval and a distinct runtime `active` state;
- named content-owner department, approver, and approval timestamp;
- a completed source check and a future review due date;
- matching expected and observed SHA-256 digests;
- release from quarantine;
- no unresolved conflict.

Time-sensitive operational sources require short, owner-approved review periods.
Overdue review, a future check timestamp, hash mismatch, conflict, or kill-switch
quarantine blocks every dependent record.

## Record activation

An answerable record additionally requires:

- approved and active states on the record itself;
- the requested language and a matching active source ID;
- owner and approval evidence;
- a current validity window and future review date;
- a current source-check timestamp;
- an exact SHA-256 digest of the question and answer fields;
- no record conflict or quarantine flag;
- `valid_until` for time-sensitive content.

Pending Uzbek FAQ candidates are non-retrievable. Russian and English translation
drafts require separate approval and activation; the system must never silently treat
translation as inherited approval. Legal summaries also remain unavailable until the
responsible legal/content owner approves the exact wording and citation.

## Conflict policy

When a department candidate conflicts with an official source, both references are
recorded in a review item and the candidate is quarantined. Retrieval returns no
factual answer from it. An LLM cannot choose the prevailing source or resolve the
conflict.

## Stage 2 review-package status

Stage 2 candidate files are offline human-review artifacts under `data/knowledge`.
They are not loaded by the application runtime. The package schema requires every
record to remain `pending_review`, `inactive`, quarantined, unapproved, and
runtime-ineligible. Russian and English drafts must link to the exact Uzbek content
hash and retain independent language-review fields.

Materially conflicting source items are absent from all language packages and live
only in the machine-readable conflict report. Records with incomplete public-source
coverage are marked `pending` rather than verified. Human approval does not activate a
record; a future separately authorized stage would still need a controlled import and
activation action.
