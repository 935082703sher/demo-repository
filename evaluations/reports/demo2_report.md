# Demo 2 Multilingual Evaluation Report

This report is generated from synthetic fixtures only. No external provider call or
real citizen data is used.

## Result

- Cases: 60/60 passed
- Critical hallucinations: 0
- Category accuracy: 100.00%
- Language correctness: 100.00%
- Out-of-scope refusal accuracy: 100.00%
- Grounded-answer rate: 100.00%
- Citation validity: 100.00%
- Unsupported-question refusal rate: 100.00%
- Human-handoff correctness: 100.00%

## Results by language

| Language | Passed | Total |
|---|---:|---:|
| uz | 20 | 20 |
| ru | 20 | 20 |
| en | 20 | 20 |

## Performance and usage

- Average end-to-end test latency: 1.223 ms
- P95 end-to-end test latency: 1.714 ms
- Provider attempts: 20
- Input tokens reported by the deterministic provider: 216
- Output tokens reported by the deterministic provider: 108
- Estimated configured test cost: 0.00086400

Latency is local TestClient measurement, not production latency. Token and cost values
are deterministic synthetic measurements that prove accounting behavior; they do not
forecast an approved provider or production bill.

## Safety acceptance

Demo 2 passes the evaluation safety gate only when all 60 cases pass and the critical
hallucination count is zero. Official registration remains disabled in every case.
