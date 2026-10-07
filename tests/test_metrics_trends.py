"""Windowed KPI trends: prove the dashboard reflects quality over time."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.services.audit_log import (
    OUTCOME_CALL_1170,
    OUTCOME_LC_SUCCESS,
    OUTCOME_RESOLVED,
    AuditEvent,
    InMemoryAuditLog,
    compute_trends,
)

_NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _ev(outcome: str, days_ago: int) -> tuple[datetime, str]:
    return (_NOW - timedelta(days=days_ago), outcome)


def test_window_kpis_reflect_recent_improvement() -> None:
    # Old week: mostly routed to 1170. Recent days: mostly resolved.
    events = (
        [_ev(OUTCOME_CALL_1170, 40) for _ in range(8)]
        + [_ev(OUTCOME_RESOLVED, 2) for _ in range(9)]
        + [_ev(OUTCOME_LC_SUCCESS, 1) for _ in range(1)]
    )
    trends = compute_trends(events, now=_NOW, windows=(7, 90))
    windows = cast(dict[str, dict[str, Any]], trends["windows"])
    w7 = windows["7d"]
    w90 = windows["90d"]
    # The last 7 days are wins; the 90-day window is dragged down by the old 1170s.
    assert w7["self_service_resolution_rate"] == 1.0
    assert w90["self_service_resolution_rate"] is not None
    assert w90["self_service_resolution_rate"] < w7["self_service_resolution_rate"]
    assert w7["call_1170_rate"] == 0.0


def test_daily_series_covers_the_window_and_is_ordered() -> None:
    trends = compute_trends([_ev(OUTCOME_RESOLVED, 0)], now=_NOW, bucket_days=14)
    daily = cast(list[dict[str, Any]], trends["daily"])
    assert len(daily) == 14
    dates = [d["date"] for d in daily]
    assert dates == sorted(dates)  # chronological
    assert daily[-1]["date"] == _NOW.date().isoformat()
    assert daily[-1]["self_service_resolution_rate"] == 1.0


def test_empty_window_yields_null_rates_not_fake_numbers() -> None:
    trends = compute_trends([], now=_NOW)
    w7 = cast(dict[str, dict[str, Any]], trends["windows"])["7d"]
    assert w7["self_service_resolution_rate"] is None
    assert w7["total_events"] == 0


def test_inmemory_log_trends_from_recorded_events() -> None:
    log = InMemoryAuditLog()
    asyncio.run(log.record(AuditEvent(channel="web", language="uz", outcome=OUTCOME_RESOLVED)))
    asyncio.run(log.record(AuditEvent(channel="web", language="uz", outcome=OUTCOME_CALL_1170)))
    trends = asyncio.run(log.trends())
    w7 = cast(dict[str, dict[str, Any]], trends["windows"])["7d"]
    assert w7["total_events"] == 2
    assert w7["self_service_resolution_rate"] == 0.5
