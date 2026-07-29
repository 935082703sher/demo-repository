# Next Phases

Future work is intentionally documented but not implemented.

1. Obtain reviewed RTMC FAQ, service, contact, and regulatory records with owner,
   approval/effective/review dates, language, version, status, and official source.
2. Agree the authenticated Nuxt-backend API contract, session boundary, rate limits,
   timeouts, origins, and deployment URLs.
3. Decide whether an RTMC-approved external LLM or internal model may process citizen
   text; complete data-location, retention, redaction, contract, and evaluation review.
4. Design an approved ingestion/review lifecycle and PostgreSQL metadata store. Select
   pgvector or another approved retrieval system only after evidence-volume testing.
5. Approve category fields, multilingual fixed wording, privacy/consent notice, retention,
   audit access, and deletion behavior.
6. Specify and staff the human-operator queue, including approved emergency contacts,
   escalation priorities, minimum transfer fields, status, and failure handling.
7. Obtain the official appeal API contract: backend authentication, exact required
   fields, idempotency, timeout/retry behavior, official confirmation semantics, and test
   environment. Only the official system may create case number, department, or status.
8. Add operational controls: authentication/authorization, rate limiting, kill switch,
   structured audit store, metrics, tracing, alerts, backup/restore, rollback, dependency
   scanning, API security tests, and load tests.
9. Complete staging integration, multilingual content review, hallucination and injection
   evaluations, accessibility/user acceptance, security approval, and written service-owner
   risk acceptance before any citizen-facing release.

Inputs currently blocking the next phase are approved knowledge, provider/data-governance
decision, database/retrieval decision, website integration contract, human-handoff
workflow, approved privacy wording, emergency configuration, and official appeal API
specification.
