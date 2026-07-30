# Demo 2 Evaluation Plan

## Dataset

`evaluations/cases/demo2_cases.json` contains exactly 60 synthetic cases:

- 20 Uzbek;
- 20 Russian;
- 20 English.

The cases cover all six categories, supported synthetic knowledge, unsupported factual
questions, ambiguity, out-of-scope topics, injection, legal requests, emergency,
credentials, explicit language change, quota exhaustion, provider failure,
expired/inactive knowledge, and fabricated citations.

## Execution

```bash
python -m evaluations.run
```

The runner creates:

- `evaluations/reports/demo2_report.json`;
- `evaluations/reports/demo2_report.md`.

Every case uses an isolated FastAPI application and a deterministic provider or
failure double. No network or paid call is permitted.

## Metrics

The suite reports:

- category accuracy;
- active-language correctness;
- out-of-scope refusal accuracy;
- grounded-answer rate;
- citation validity;
- unsupported-question refusal rate;
- human-handoff correctness;
- critical hallucination count;
- average and P95 local latency;
- actual provider attempts;
- reported input/output tokens;
- configured estimated cost.

The cost settings used by evaluation are synthetic and exist only to prove accounting.

## Acceptance

Demo 2 fails evaluation when any case fails or the critical hallucination count is
greater than zero. A critical hallucination includes an official-registration claim,
non-null case number, grounded answer without a source, or leakage of a fabricated
citation.
