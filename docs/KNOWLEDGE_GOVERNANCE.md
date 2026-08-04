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

## Stage 1 status

Only strict models, policies, and synthetic tests are present. No real source or
record is committed, approved, or active. Stage 2 may create pending candidates only;
activation still requires the RTMC decisions listed in the Demo 3 implementation
package.
