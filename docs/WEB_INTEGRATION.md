# Web Integration Guide (for the website/backend developer)

This is everything you need to wire the official RTMC website to the AI Assistant
service. You do not need to understand the internal AI/RAG implementation.

> **Status:** local test/demo build. It cannot register an official appeal or
> generate an official case number. Treat every response as draft guidance only.

## Base URL

- Local development: `http://127.0.0.1:8000` (or `http://localhost:8000` when run
  via Docker Compose).
- Production URL: to be assigned when this service is deployed.

## Authentication

None today. This is a local demo. Before production deployment, add
authentication/network restriction in front of the service (e.g. gateway API key or
internal network only) — this is not yet implemented.

## Endpoint: chat

`POST /api/v1/chat`

Request body:

```json
{
  "session_id": null,
  "language": "uz",
  "message": "IMEI ro'yxatdan o'tkazish haqida ma'lumot bering"
}
```

- `session_id` (optional): a UUID. Omit it on the first message; the server returns
  a generated UUID in the response — send that same value back on every following
  message in the conversation to keep session state (language, clarification count,
  usage quota).
- `language` (optional): `"uz"`, `"ru"`, or `"en"`. If omitted and no session exists
  yet, the server replies with `state=language_selection` and asks the citizen to
  pick one. Once a session has a language, you do not need to resend it.
- `message` (required): 1–4000 characters, trimmed server-side.

Response body (always HTTP 200 unless rate-limited, see below):

```json
{
  "request_id": "…",
  "session_id": "…",
  "language": "uz",
  "state": "answer",
  "response_type": "answer",
  "category": "imei",
  "reply": "…citizen-facing text…",
  "grounded": true,
  "sources": [
    {"document_id": "…", "title": "…", "url": null, "version": "…", "demo_only": true}
  ],
  "fields_collected": {},
  "fields_missing": [],
  "draft": null,
  "consent_required": false,
  "submission_allowed": false,
  "requires_human": false,
  "handoff_reason": null,
  "safety_flags": [],
  "human_handoff_available": false,
  "officially_registered": false,
  "case_number": null
}
```

Field meaning for the frontend:

- `reply`: the only text you need to render as the assistant's message bubble.
- `grounded` + `sources`: when `grounded` is `true`, the answer is backed by an
  approved/demo knowledge record; show the `sources` list as citations. When
  `false`, there is no approved source — the assistant is explicitly saying it does
  not know, not guessing.
- `state` / `response_type`: drive UI branching. Common values:
  - `answer` — grounded knowledge answer.
  - `follow_up` — assistant needs more information; `fields_missing` lists which
    structured fields are still needed (render as a normal chat prompt, the citizen
    can just reply in free text).
  - `refusal` — out-of-scope request (politely declined).
  - `human_handoff` — hand off to a human operator; `requires_human=true` and
    `handoff_reason` explains why (safety issue, no approved source, unclear after
    clarification, etc.).
  - `language_selection` — ask the citizen to choose uz/ru/en.
  - `usage_limit_reached` / `rate_limited` — see below.
- `officially_registered` is always `false` and `case_number` is always `null` in
  this build. **Never render UI copy implying an official complaint number exists.**
- `consent_required` / `submission_allowed`: reserved for the complaint-draft flow
  (see below); always `false`/`false` on plain chat turns.

### Errors

- `422` — request validation error (bad JSON, message too long/empty, invalid
  language code). Body: `{"error": {"code", "message", "request_id", "details"}}`.
- `429` — rate limited (20 requests/minute/session by default). Body is a typed
  `rate_limited` response plus a `Retry-After` header (seconds).
- `500` — unexpected server error. Body follows the same `ErrorResponse` envelope;
  no internal detail is exposed.

Every response (success or error) carries an `X-Request-ID` header — log it
alongside any support ticket.

## Endpoint: health check

`GET /health` → `200 {"status":"ok","service":"rtmc-ai-assistant","version":"…"}`.
Use this for uptime monitoring/load-balancer health checks.

## Endpoint: complaint drafts (optional, advanced)

The chat endpoint already walks a citizen through a structured complaint via normal
conversation turns (`follow_up` responses). If your frontend wants a dedicated
"review before sending" screen instead, use:

- `POST /api/v1/complaints/draft` — create/update a versioned draft.
- `GET /api/v1/complaints/{draft_id}` — fetch current draft.
- `DELETE /api/v1/complaints/{draft_id}` — cancel a draft.
- `POST /api/v1/complaints/{draft_id}/submit` — record explicit citizen consent.

**Submitting a draft never contacts a real RTMC backend in this build.**
`officially_registered` remains `false` and no case number is issued. Do not show
citizens a message claiming their complaint was officially registered. Full request/
response shapes are documented in [`docs/API_CONTRACT.md`](API_CONTRACT.md).

## Language handling

The assistant replies in whatever `language` the session was started with. If your
frontend already knows the citizen's language (site locale), always send it
explicitly — you do not need to build your own language detection.

## Session handling

- Sessions are in-memory and process-local; they disappear on server restart. Do
  not persist `session_id` as a durable citizen identifier.
- Keep the same `session_id` for the whole conversation so follow-up questions and
  usage quotas work correctly. Start a new one for a new conversation.

## Source/reference format

Each item in `sources` is:

```json
{"document_id": "DEMO-EN-IMEI-001", "title": "…", "url": null, "version": "…", "demo_only": true}
```

`demo_only: true` means the citation is a synthetic fixture, not real approved RTMC
content — render this distinctly (e.g. a "demo" badge) if you show it during this
test phase. Once real approved content ships, `demo_only` will be `false` and `url`
will point at the approved source.

## CORS (local development)

The service enables CORS for these origins by default:
`http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5173`,
`http://127.0.0.1:5173` (common Nuxt/Vite dev ports).

Override with the `CORS_ALLOWED_ORIGINS` environment variable (comma-separated list
of exact origins) — set it to your production website origin before deployment.
Setting it to an empty value disables the CORS middleware entirely (same-origin only).

## Local development

```bash
docker compose up --build
# or: make demo
```

Then point your frontend dev server at `http://127.0.0.1:8000`.

## What is intentionally NOT implemented yet

- Real approved RTMC knowledge (current knowledge base is synthetic demo fixtures
  only, clearly marked `demo_only: true`).
- Official complaint submission to a real RTMC backend/case-tracking system.
- Authentication/API keys in front of the service.
- Persistent session/draft storage (everything is in-memory and resets on restart).
