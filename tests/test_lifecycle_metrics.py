"""Resolution-lifecycle KPIs in the audit metrics."""

from __future__ import annotations

import asyncio
from collections import Counter

from app.services.audit_log import (
    OUTCOME_CALL_1170,
    OUTCOME_LC_FAILURE,
    OUTCOME_LC_SUCCESS,
    OUTCOME_LC_UNCLEAR,
    AuditEvent,
    InMemoryAuditLog,
    compute_metrics,
)


def test_compute_metrics_lifecycle_rates() -> None:
    outcomes: Counter[str] = Counter(
        {
            OUTCOME_LC_SUCCESS: 6,
            OUTCOME_LC_FAILURE: 2,
            OUTCOME_LC_UNCLEAR: 2,
            OUTCOME_CALL_1170: 1,
        }
    )
    m = compute_metrics(outcomes, Counter())
    assert m["lifecycle_results"] == 10
    assert m["ai_resolution_rate"] == round(6 / 7, 4)  # success vs (success + 1170)
    assert m["first_result_success_rate"] == 0.6
    assert m["unclear_outcome_rate"] == 0.2
    assert m["call_1170_count"] == 1


def test_inmemory_tracks_failure_cards_styles_and_reasons() -> None:
    log = InMemoryAuditLog()

    async def run() -> dict[str, object]:
        await log.record(
            AuditEvent("web", "uz", OUTCOME_LC_FAILURE, card_id="imei-register", style="simple")
        )
        await log.record(
            AuditEvent(
                "web", "uz", OUTCOME_LC_FAILURE, card_id="imei-register", style="step_by_step"
            )
        )
        await log.record(AuditEvent("web", "uz", OUTCOME_LC_SUCCESS, card_id="imei-clone"))
        await log.record(
            AuditEvent("web", "uz", OUTCOME_CALL_1170, detail="all_safe_paths_exhausted")
        )
        return await log.metrics()

    m = asyncio.run(run())
    assert m["cards_failing_most"] == {"imei-register": 2}
    assert m["explanation_style_distribution"] == {"simple": 1, "step_by_step": 1}
    assert m["call_1170_reasons"] == {"all_safe_paths_exhausted": 1}
