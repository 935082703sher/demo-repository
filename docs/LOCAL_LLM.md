# Local LLM (Ollama) — Self-Hosted Inference for Development/Test

## 1. What Ollama is doing in this project

`LLM_PROVIDER=ollama` selects `app/providers/ollama.py` (`OllamaProvider`), which sends
the already-retrieved, already-approved context passages to a locally running Ollama
server and asks it to compose the citizen-facing answer. It implements the exact same
`LLMProvider` protocol as the mock and OpenAI adapters
(see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)), so nothing in the chat/RAG/governance
layers changes: retrieval still happens first, the model is still only ever called with
context the server already approved, and every citation it returns is still validated
against the server-owned source IDs afterward. If no approved knowledge record matches
the citizen's question, the model is **never invoked** — the existing safe refusal/
human-handoff path runs exactly as it does with the mock provider.

## 2. Inference is local/self-hosted

Ollama runs as a local process on your machine (or, in production, on RTMC's own GPU
server). The FastAPI service talks to it over plain HTTP on your local network/loopback
interface. Nothing about a citizen's message or the generated answer leaves that
network boundary.

## 3. No OpenAI/Claude API is required

`LLM_PROVIDER=ollama` needs no API key of any kind. The `OllamaProvider` never calls
`api.openai.com`, `api.anthropic.com`, or any other external endpoint — only the
`OLLAMA_BASE_URL` you configure. The existing OpenAI adapter (`llm_provider=openai`)
still exists in the codebase for future use if RTMC ever approves an external provider,
but it is not used or required here.

## 4. Install/start Ollama

macOS:

```bash
brew install ollama
# or download the app from https://ollama.com/download
ollama serve   # if it is not already running as a background service
```

Check it's running:

```bash
curl -s http://127.0.0.1:11434/api/version
```

## 5. Obtain the development model

This project defaults to **`qwen3:8b`** (Qwen3, 8B parameters, Q4_K_M quantization —
about **5.2 GB** on disk). Pull it once:

```bash
ollama pull qwen3:8b
```

Why this model: it was already present on the development machine used to build this
integration, so it required no additional download; it is well below the "do not use a
27B/30B/32B model for a local test" guidance; it produced correct, on-topic,
schema-valid JSON output in every test performed here (including Uzbek and Russian); and
Qwen is a widely supported open-weight family with a clear path to larger siblings if
the RTMC GPU server can host one later. If you don't have it locally and want something
smaller/faster to pull, `qwen2.5:3b-instruct` (~1.9 GB) or `qwen2.5:1.5b-instruct`
(~1 GB) also work with this adapter — just set `OLLAMA_MODEL` accordingly. Quality on
Uzbek/Russian will be lower with the smaller models; the governance/citation gate still
applies regardless of model choice.

**This is a development/test model choice only.** The final production model will be
selected after RTMC's GPU specifications are confirmed (see
[`docs/MODEL_BASELINE_PLAN.md`](MODEL_BASELINE_PLAN.md)).

## 6. Configure the application

In `.env` (copy from `.env.example`):

```bash
LLM_PROVIDER=ollama
LLM_TIMEOUT_SECONDS=60          # raise from the 15s default — local inference is slower
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_TIMEOUT_SECONDS=60
```

`LLM_TIMEOUT_SECONDS` is the outer bound enforced by `GroundedGenerationService`
(applies to every provider); `OLLAMA_TIMEOUT_SECONDS` is the adapter's own HTTP client
timeout. Keep both set to a comparable value — the shorter of the two is what actually
applies.

## 7. Start FastAPI locally (native)

```bash
python3.12 -m venv /tmp/rtmc-ai-assistant-venv
. /tmp/rtmc-ai-assistant-venv/bin/activate
pip install -e '.[dev]'
LLM_PROVIDER=ollama LLM_TIMEOUT_SECONDS=60 make run
```

## 8. Start FastAPI through Docker

```bash
LLM_PROVIDER=ollama docker compose up --build
```

Leaving `LLM_PROVIDER` unset keeps the existing default (`mock`) — Docker behavior is
unchanged unless you explicitly opt in.

## 9. How Docker reaches host Ollama

`compose.yaml` maps `host.docker.internal` to the host gateway
(`extra_hosts: host.docker.internal:host-gateway`) and defaults
`OLLAMA_BASE_URL` to `http://host.docker.internal:11434` **inside the container only**
(the native default, `127.0.0.1:11434`, would point at the container itself, not your
Mac). This was verified directly, not assumed:

```bash
docker compose exec api python3 -c \
  "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags', timeout=5).status)"
# -> 200
```

and confirmed end-to-end via the container logs showing a real outbound call:
`HTTP Request: POST http://host.docker.internal:11434/api/chat "HTTP/1.1 200 OK"`.

If you need a different Ollama host/port, override `OLLAMA_BASE_URL` in the shell before
`docker compose up`, e.g. `OLLAMA_BASE_URL=http://192.168.1.50:11434`.

## 10. Test the three languages

```bash
curl -s http://127.0.0.1:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"language":"uz","message":"IMEI demo manba ko'"'"'rsat"}'

curl -s http://127.0.0.1:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"language":"ru","message":"Покажи IMEI демо источник"}'

curl -s http://127.0.0.1:8000/api/v1/chat -H 'Content-Type: application/json' \
  -d '{"language":"en","message":"Show the IMEI demo fixture"}'
```

Each should return `"grounded": true` with a real (locally generated, non-verbatim)
answer and the correct source citation. A realistic unsupported question, e.g.
`"What is the IMEI registration fee?"`, must still return `"grounded": false` and
`"handoff_reason": "no_approved_source"` — the model is never even called for it,
because retrieval finds no approved record first.

Or use the demo page at <http://127.0.0.1:8000/> — type a question and watch a real
locally generated answer come back.

## 11. Stop services

```bash
docker compose down      # if running via Docker
# Ctrl+C the uvicorn process if running natively
# Ollama itself can keep running in the background for reuse; to stop it:
#   macOS app: quit from the menu bar icon
#   brew service: brew services stop ollama
```

## 12. Known limitations

- Local CPU inference is slower and lower-quality than a cloud frontier model or a
  GPU-hosted production deployment; expect single-digit-second latency per answer on a
  developer Mac (observed: ~1.3–2.8s per grounded answer with `qwen3:8b` and thinking
  mode disabled).
- The first request after Ollama (re)starts or after switching models may be slower
  while the model loads into memory; it stays warm for reuse afterward (Ollama's
  default `keep_alive` window).
- The adapter requires the model to return valid JSON matching the requested schema;
  if it doesn't, the request fails safely (`ProviderOutputError` → human handoff) rather
  than surfacing malformed text to a citizen.
- Ollama, like every provider behind this protocol, can only be trusted as far as the
  citation check verifies — it proves the answer *cites* an approved source, not that
  every sentence is entailed by it. Keep approved-context passages short and specific
  for this reason (already true of the existing demo fixtures).
- No fine-tuning has been performed; see
  [`docs/MODEL_BASELINE_PLAN.md`](MODEL_BASELINE_PLAN.md).

## 13. Future migration path: RTMC GPU + vLLM

```text
Today (dev/test):  FastAPI service -> OllamaProvider -> Ollama -> qwen3:8b (or similar)
Later (production): FastAPI service -> a vLLM-compatible provider -> vLLM on RTMC GPU server -> selected open-weight model
```

Both Ollama and vLLM can expose an OpenAI-compatible chat endpoint, so a future vLLM
adapter can likely reuse most of `OllamaProvider`'s request/response shape (or even the
existing `OpenAIResponsesProvider`'s structured-output pattern against vLLM's
OpenAI-compatible API) with a small, isolated new adapter — no change to
`AssistantService`, retrieval, or grounding. This is intentionally not built yet
(Phase 6 in this task explicitly asked to prioritize getting Ollama working today); the
protocol boundary already supports it without rework.
