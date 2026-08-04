# RTMC AI Assistant — Demo 3 Scope

## Status and baseline

Demo 3 is an internal staging exercise for approved-knowledge governance and
appeal-draft preparation. It is not production-ready and must not be exposed to
citizens.

Development starts from the immutable Demo 2 baseline:

- commit: `382635bd16d83f754fc3b57c52a4b51465df48a3`;
- annotated tag: `v0.2.0-demo2`;
- development branch: `demo3-approved-content-staging`.

Demo 1 remains frozen at `v0.1.0-demo1`, resolving to
`32b7b0e96260b1d7aa85cbbb5f1ad6bc19e4769b`. Release tags must not be moved,
deleted, or recreated.

The repository has no `rules.md` or `skills.md`. Their absence was reviewed and is
not a recovery blocker. `AGENTS.md`, existing repository documentation, and the
approved Demo 3 implementation package govern this stage.

## Current implementation boundary

This branch currently implements Stage 0 and Stage 1 only:

- confidential-source quarantine paths and Git exclusions;
- strict source manifests and streaming SHA-256 verification;
- archive-member validation and safe local ZIP extraction;
- a local-only document/PDF extraction interface whose policy cannot enable network;
- conservative PII detection and a committed-fixture build gate;
- separate source/record approval and activation lifecycles;
- fail-closed validity, review, conflict, language, and content-hash checks;
- synthetic security, privacy, failure, and lifecycle tests.

No supplied departmental content is parsed into records. No real record is active.
The application version remains `0.2.0` until Demo 3 acceptance and freeze.

## Included in later approved stages

Later stages may add pending FAQ candidates, legal workflow mapping, PostgreSQL and
Redis staging implementations, structured appeal-draft persistence, disabled/sandbox
submission, expanded synthetic evaluation, and the Nuxt staging contract. Each stage
requires an explicit continuation command and its own verification boundary.

## Excluded

Demo 3 does not authorize:

- public deployment or real citizen submissions;
- production credentials, databases, or appeal-system connectivity;
- automatic legal decisions, routing, transfer, rejection, or deadline calculation;
- real case numbers or inferred official status;
- raw PII, full identifiers, attachments, or confidential source text in provider calls;
- unapproved FAQ, legal summaries, translations, contacts, fees, or procedures;
- real attachment upload before approved storage, scanning, retention, and access rules.

Every submission path must continue to enforce:

```json
{
  "officially_registered": false,
  "case_number": null,
  "official_status": null
}
```

## Stage boundary

Stage 2 may begin only after Stage 0–1 evidence is accepted and the user explicitly
requests it. Until then, quarantined files remain unopened and no FAQ candidate,
translation, legal summary, or real-content answer is created.
