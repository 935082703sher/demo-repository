# Demo 2 Provider Decision

## Decision

The provider boundary remains vendor-independent and the deterministic `mock` provider
remains the default. Demo 2 includes one concrete OpenAI Responses API adapter solely
to prove configuration, structured output, timeout, retry, citation, and measurement
behavior.

This is not RTMC approval of OpenAI, a model, international data transfer, pricing, or
paid use. Selecting `openai` without both a model and API key produces a safe provider
handoff. No automated test makes a network call.

The adapter uses the Responses API and strict JSON-schema output. OpenAI documents the
Responses endpoint and structured-output support in its official developer
documentation:

- <https://developers.openai.com/api/docs/models>
- <https://developers.openai.com/api/docs/guides/latest-model>

## Configuration

```text
LLM_PROVIDER=mock
LLM_MODEL=
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=15
LLM_MAX_OUTPUT_TOKENS=500
LLM_MAX_RETRIES=1
LLM_INPUT_COST_PER_MILLION=0
LLM_OUTPUT_COST_PER_MILLION=0
```

No model is chosen by default. Cost rates default to zero rather than embedding a price
that may become stale. RTMC must configure approved rates for estimates to be
meaningful.

## Security behavior

- The API key is environment-backed `SecretStr`, is never returned, and is not logged.
- Only the question, language, category, and minimum retrieved context are sent.
- Common email addresses and long digit sequences are redacted from the question.
- The request sets `store: false`; RTMC must still approve the provider contract,
  retention, processing location, and transfer conditions.
- The adapter requests only server-supplied source IDs and structured citations.
- Provider output is untrusted and remains subject to backend citation and safety
  validation.
- Authentication, malformed output, timeout, and availability errors expose only safe
  generic handoff behavior.

## Retries and usage

`LLM_MAX_RETRIES` is bounded to 0–3. One user request consumes one logical quota unit,
while every actual provider attempt is counted. Input/output tokens, cumulative
latency, success/failure, and estimated cost are recorded in process-local technical
usage state.

## Approval required

Before any real call, RTMC must approve the vendor, model, contract, data fields,
retention, processing locations, secret management, pricing, budgets, monitoring, and
incident response. The Demo 2 repository does not activate or verify those approvals.
