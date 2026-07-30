# Demo 2 Usage Protections

Demo 2 uses two independent server-owned controls.

## LLM-generation quota

`LLM_GENERATION_LIMIT_PER_SESSION` defaults to 10 logical generations per
`LLM_QUOTA_WINDOW_SECONDS`, which defaults to 86,400 seconds.

A logical allowance unit is consumed atomically only after deterministic safety,
scope, category, complaint-follow-up, and approved-knowledge checks show that an
external generation is required. Clear refusals, language selection, deterministic
follow-up, missing-source handoff, draft operations, Submit, and human escalation do
not consume this allowance.

Provider retries remain one logical user allowance but each actual attempt is measured
separately. The backend ignores the optional browser-reported `llm_usage_count`; it is
accepted only for compatibility and never used for authorization.

After exhaustion, the chat API returns `usage_limit_reached` without calling the
provider. Complaint draft review, edit, cancel, consent, and Demo Submit endpoints
remain available. Demo Submit still cannot register an appeal.

## Request-rate protection

`REQUEST_RATE_LIMIT_PER_MINUTE` defaults to 20 valid chat requests per session. It is a
separate sliding-minute limiter and returns HTTP 429 with `Retry-After` and a localized
typed body. It does not use IP address as the sole identity.

## Contact safety

Only `APPROVED_SUPPORT_PHONE` and `APPROVED_CONTACT_URL` may appear in a quota message.
When only the URL is configured, no phone placeholder is shown. When neither is
configured, the response gives neutral human-handoff guidance without inventing a
contact.

## Demo limitations

Both repositories are process-local. Restarting the application clears their state,
multiple workers do not share counters, and a user can bypass session-based limits by
starting a new session. A production design requires authenticated identity where
appropriate and centralized storage or gateway-level enforcement.
