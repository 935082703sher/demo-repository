# Security Notes

## Threat assumptions

Citizen input, uploaded/retrieved text, and provider output are untrusted. Demo 2 assumes
an attacker may attempt prompt injection, secret disclosure, oversized input, unsupported
fact requests, duplicate submission, stale-version consent, or fabricated official claims.

## Enforced controls

- strict Pydantic models reject malformed, empty, oversized, unsupported-language, and
  undeclared fields;
- deterministic rules stop obvious credentials, prompt injection, danger, threats,
  self-harm, serious cybersecurity reports, and legal-interpretation requests;
- user input is never loaded into the knowledge repository;
- retrieval filters language, category, approval metadata, source URL, activity,
  validity, content hash, synthetic marking, and keyword evidence;
- deterministic scope refusal occurs before provider generation;
- independent server-owned request-rate and logical-generation limits protect usage;
- provider prompts contain only minimum retrieved context and common identifiers in
  factual questions are redacted;
- provider output must be structured and cite only supplied source IDs;
- output checks block obvious case-number, registration, decision, and guarantee claims;
- the default mock provider has no tools or network; the configured real adapter is
  unavailable without explicit model/key configuration;
- draft updates use optimistic version checks and new content hashes;
- consent binds the exact version/hash, notice version, request ID, timestamp, and
  idempotency key;
- duplicate Submit events cannot create official activity;
- logs include metadata but never intentionally include full message/draft content;
- the Docker process runs without root privileges.

These controls do not constitute complete threat detection. Keyword safety rules are a
demo mechanism and require evaluated production replacements or layered controls.

## Data restrictions

Do not use real citizen data. The API rejects undeclared identity fields, including a
full IMEI. Do not add password, PIN, OTP, bank-card, token, private-key, or unrelated
identity-document fields. The process-local store has no retention guarantee and should
not be treated as an official record.

## Secrets

Demo 2 defaults to mock and needs no API key or database credential. `.env.example`
contains empty secret placeholders and non-secret defaults only. A real key is accepted
only from the environment and stored as `SecretStr`; it is never logged or returned.
Production secrets require an RTMC-approved secret manager.

## Logging

Request metadata contains request ID, endpoint, method, status, and duration. Expected
workflow errors return safe codes. Unexpected errors are logged server-side, while the
client receives a generic message. Production requires access controls, tamper resistance,
retention, redaction review, monitoring, and incident procedures.

## Production work not implemented

Authentication, authorization, HTTPS termination, distributed/authenticated limits,
gateway controls, CSRF/origin policy, attachment scanning, encrypted persistence,
backups, audit storage, staffed handoff, kill switch, dependency scanning, penetration
testing, and formal privacy/legal/provider approval are required before external use.
