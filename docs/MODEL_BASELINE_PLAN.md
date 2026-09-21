# Model Baseline Evaluation Plan

**No fine-tuning has been performed, and none should be, until this baseline exists.**
This document defines how we will decide whether fine-tuning is even justified — it is
a plan, not a result. Today's integration work (Ollama provider, `qwen3:8b`) proves the
*pipeline* works end-to-end; it is not a claim about model quality, and no
production model decision should be made from it.

## Why measure before fine-tuning

Fine-tuning is expensive to build, evaluate, and maintain (data curation, training
compute, re-evaluation on every base-model update). It is only worth doing if a
measured baseline shows the *un*-tuned model has a specific, quantified gap that
fine-tuning is the right tool to close — and not, for example, a gap that better
retrieval, better prompting, or a larger base model would close more cheaply. Skipping
straight to fine-tuning without this baseline risks solving a problem we haven't
confirmed exists, in a way that's hard to undo.

## Process

```text
candidate models
  -> baseline without fine-tuning
  -> multilingual evaluation (uz / ru / en)
  -> RTMC domain evaluation
  -> hallucination/grounding evaluation
  -> latency
  -> VRAM
  -> throughput
  -> compare results
  -> only then decide whether fine-tuning is justified
```

### 1. Candidate models

Start with open-weight instruct models already compatible with this project's provider
boundary (Ollama today, vLLM later), spanning a size range appropriate to whatever GPU
RTMC ultimately provisions. Qwen, Llama, and Gemma instruct families are reasonable
starting candidates given multilingual (including Uzbek/Russian) support claims; the
actual candidate list should be finalized once RTMC's GPU specs are known.

### 2. Baseline without fine-tuning

Run every candidate through the existing `AssistantService` pipeline exactly as-is —
same retrieval, same grounding validator, same prompt — via each model's own provider
adapter. No prompt engineering beyond what's already required for structured JSON
output. This is the number every later comparison (including a fine-tuned variant, if
one is ever built) must beat to be worth shipping.

### 3. Multilingual evaluation

Reuse and extend the existing 60-case evaluation suite
(`evaluations/cases/demo2_cases.json`, `evaluations/run.py`) across Uzbek, Russian, and
English. Track per-language pass rate separately — a model that's strong in English but
weak in Uzbek is not acceptable for this project regardless of its aggregate score.

### 4. RTMC domain evaluation

Once real approved RTMC knowledge exists (see `docs/KNOWLEDGE_GOVERNANCE.md` /
`docs/DEMO3_STAGE2_*`), build a held-out set of realistic citizen questions with known
correct grounded answers, drawn from that approved content. Score answer correctness
against the approved source, not against the model's general knowledge.

### 5. Hallucination/grounding evaluation

Adversarial cases specifically designed to tempt the model into inventing fees,
deadlines, phone numbers, addresses, procedures, or complaint/case IDs not present in
the supplied context — mirroring the existing
`test_unsupported_factual_question_has_no_answer`-style tests but at model-comparison
scale. A model that ever fabricates one of these fails this gate regardless of how
fluent it otherwise is; the deterministic `GroundingValidator` citation check is a
safety net, not a substitute for measuring this directly.

### 6. Latency

Measure end-to-end request latency (server-side, as already logged via the
`request_id=... duration_ms=...` structured log line) at realistic context sizes, both
cold (first request) and warm.

### 7. VRAM

Measure peak VRAM/RAM at the target quantization level for each candidate, since this
directly constrains which models fit on the eventual RTMC GPU.

### 8. Throughput

Measure concurrent-request throughput at the expected citizen traffic pattern (this
service's existing rate limits — 20 requests/minute/session by default — give a rough
floor, not a ceiling, for what production throughput needs to support).

### 9. Compare results

Put every candidate's results from steps 3–8 side by side. No candidate advances to a
fine-tuning discussion without this comparison existing in writing.

### 10. Only then decide whether fine-tuning is justified

Fine-tuning is considered only if the comparison in step 9 shows a specific, reproducible
gap (e.g., a particular language's grounding-evaluation pass rate, or a domain-specific
phrasing failure) that prompting/retrieval improvements can't close, and the gap is
large enough to justify the ongoing cost of maintaining a fine-tuned model. If that
point is reached, the next step is a separate scoped proposal — not something this
document authorizes on its own.
