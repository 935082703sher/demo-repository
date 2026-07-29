# Demo 1 Scope

## Included

Demo 1 proves that a Python/FastAPI service can:

- receive and validate typed JSON chat requests;
- support `uz`, `ru`, and `en`, or request a language choice;
- classify `imei`, `mnp`, `number_codes`, `network_quality`, `website_issue`, and `other`;
- run deterministic safety and scope checks;
- search only active local `approved` or explicitly synthetic `demo_only` records;
- refuse unsupported factual answers and require human review;
- ask category-specific follow-up questions;
- create, review, edit, version, retrieve, and cancel process-local complaint drafts;
- bind explicit consent to a draft version, hash, privacy-notice version, and idempotency key;
- return a safe non-registration result from the Demo Submit endpoint;
- expose consistent errors, tests, local execution, and Docker packaging.

## Excluded

Demo 1 does not include:

- the RTMC Nuxt widget or website backend;
- authentication, rate limiting, attachments, or real citizen data;
- a production LLM, embeddings, vector search, or document-ingestion pipeline;
- PostgreSQL, Redis, queues, microservices, or Kubernetes;
- a staffed human-operator queue or emergency contact configuration;
- an official appeal API, official case number, department, deadline, status, or notification;
- production deployment, monitoring, backups, security testing, or legal approval.

All session, clarification, draft, consent, and idempotency data is process-local and
disappears on restart. The synthetic fixture is not approved RTMC content and must be
replaced before any external or citizen-facing use.

## Governing assumptions

- The supplied `rules.md` is non-negotiable policy.
- The supplied `skills.md` defines the permitted workflow.
- No approved RTMC FAQ/service/contact/regulatory content was supplied in the workspace.
- No official appeal API contract, human queue, emergency contact, or privacy notice was
  supplied.
- The placeholder notice version `demo-privacy-v1` is a technical binding token, not
  approved citizen-facing legal text.
