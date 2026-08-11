# Demo 3 Stage 3C Local Scenarios

Run locally with:

```bash
python -m evaluations.run_stage3c_scenarios
```

The runner is not imported by any route and exposes no HTTP endpoint. It prints outcome metadata only; input messages, raw sensitive values, secure reference IDs, and consent idempotency material are excluded.

| Scenario | Expected result |
| --- | --- |
| Uzbek network-quality complaint | `review_ready` |
| Russian IMEI information request | `review_ready` |
| English MNP complaint | `review_ready` |
| Legal-entity website complaint | `review_ready`, secure identifier masked |
| Authorized-representative workflow | `clarification_required` |
| Religion request | `scope_refusal` |
| Region-based network report | `collecting`, not refused |
| Synthetic sensitive-data signal | typed handoff, queue not configured |
| Legal-deadline request | typed authority refusal/handoff |
| Edit after consent | new version and `consent_state=invalidated` |
| Cancellation | `cancelled` with no official side effect |
| Final local consent | `submission_blocked` |

All twelve scenarios use obviously synthetic values and report `officially_registered=false`, `case_number=null`, and `official_status=null`.
