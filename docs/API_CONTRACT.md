# API Contract

All bodies are JSON. Undeclared request fields are rejected. Successful API responses
include an `X-Request-ID` header; error bodies also contain the request UUID.

## `GET /health`

Returns `200`:

```json
{"status":"ok","service":"rtmc-ai-assistant","version":"0.2.0"}
```

## `POST /api/v1/chat`

Request:

```json
{
  "session_id": null,
  "language": "uz",
  "message": "Mening hududimda mobil internet juda sekin"
}
```

`language` and `session_id` are optional. A missing language returns
`state=language_selection`; a missing session creates a cryptographically random UUID.
Messages are trimmed, must not be empty, and are limited to 4,000 characters.
An explicit `language` value changes the active server-owned session language.
`llm_usage_count`, when supplied for website compatibility, is ignored for
authorization.

The stable response includes:

- request/session IDs, selected language, state, response type, and category;
- citizen-facing reply, grounding flag, and source references;
- collected/missing fields and optional full draft;
- consent and submission authorization flags;
- human-handoff reason and safety flags.
- optional limit/reset/retry fields and explicit
  `officially_registered=false`, `case_number=null`.

Authorization fields are calculated by backend code. `submission_allowed` remains
`false` in Demo 2 chat responses; deterministic complaint endpoints remain available.

Common outcomes:

- `answer`: only when an active matching record supports the provider text;
- `follow_up`: one category-specific question with missing fields;
- `refusal`: unrelated request;
- `human_handoff`: safety, unsupported evidence, repeated uncertainty, or provider failure;
- `language_selection`: language was omitted.
- `usage_limit_reached`: HTTP 200 typed response; no provider call;
- `rate_limited`: HTTP 429 typed response with `Retry-After`; no provider call.

The default logical generation allowance is 10 per session per 24 hours and the
default request rate is 20 per session per sliding minute. Both are configurable and
server-owned.

## `POST /api/v1/complaints/draft`

Create:

```json
{
  "session_id": null,
  "draft_id": null,
  "expected_version": null,
  "language": "en",
  "category": "other",
  "fields": {
    "description": "Synthetic website-access issue",
    "desired_outcome": "Responsible specialist review"
  }
}
```

Update by sending the current `draft_id`, `session_id`, and `expected_version`. Updates
merge supported fields, increment the version, create a new SHA-256 content hash, and
invalidate any earlier consent by construction.

Returns a complete review model including subject, description, every field, missing
fields, data-transfer list, version/hash, timestamps, and the “not submitted” notice.
`personal_data_to_submit` is empty because Demo 2 accepts no identity/contact fields.

## `GET /api/v1/complaints/{draft_id}`

Returns the current process-local draft or `404 draft_not_found`.

## `DELETE /api/v1/complaints/{draft_id}`

Cancels the draft. Cancelled drafts cannot be edited or submitted.

## `POST /api/v1/complaints/{draft_id}/submit`

Request:

```json
{
  "consent": true,
  "draft_version": 1,
  "privacy_notice_version": "demo-privacy-v1",
  "idempotency_key": "website-request-12345"
}
```

The endpoint requires:

- a known active and complete draft;
- `consent=true` from the dedicated website Submit action;
- the current draft version;
- the configured notice version;
- an 8–128 character idempotency key.

It records an in-memory consent event and returns `200` with
`official_integration_not_configured`. Repeating the same key returns the same semantic
result with `idempotent_replay=true`. A different key for the same draft version returns
`409 duplicate_submit`.

It never contacts an external system and never returns a case number.

## Error contract

Example:

```json
{
  "error": {
    "code": "stale_draft_version",
    "message": "Consent must be bound to the current draft version",
    "request_id": "8aa5acdf-bd49-40bd-820b-f2af02ca6bca",
    "details": null
  }
}
```

Status use:

- `404`: unknown draft;
- `409`: stale version, cancelled/incomplete draft, notice mismatch, duplicate submit;
- `422`: malformed JSON, schema violation, unsupported language/field, missing consent;
- `500`: unexpected internal failure without stack trace or secret disclosure.

Provider failures are returned as localized safe human handoff. Raw provider errors,
prompts, stack traces, keys, and model reasoning are never part of the API response.

## Versioning

The public workflow endpoints are under `/api/v1`. Backward-compatible fields may be
added within v1. Removing/renaming fields or changing their meaning requires a documented
breaking change and normally a new API version.
