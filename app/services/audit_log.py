"""Conversation audit log and the KPI metrics computed from it.

Each terminal or intermediate assistant turn is recorded as one immutable event
so pilot KPIs (self-service resolution rate, handoff rate, cost per case) can be
measured over time. The default in-memory backend needs no database; a
Postgres-backed backend is selected when a database is configured, behind the
same protocol so the application code never changes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

# Terminal and intermediate outcomes of one assistant turn.
OUTCOME_RESOLVED = "resolved"  # a resolution card was returned (self-service win)
OUTCOME_ANSWER = "answer"  # a grounded KB answer was returned (self-service win)
OUTCOME_HANDOFF = "handoff"  # escalated to a human
OUTCOME_QUESTION = "question"  # a diagnostic question was asked (in progress)
OUTCOME_CLARIFY = "clarify"  # a routing menu was offered
OUTCOME_GREETING = "greeting"  # small talk was answered

# Resolution-lifecycle outcomes: the customer's result on an offered card.
OUTCOME_LC_SUCCESS = "lc_success"  # the offered card resolved it (self-service win)
OUTCOME_LC_FAILURE = "lc_failure"  # it did not; an alternative/1170 followed
OUTCOME_LC_PARTIAL = "lc_partial"  # it helped; a remaining problem continues
OUTCOME_LC_UNCLEAR = "lc_unclear"  # the reply did not say; asked/re-explained
OUTCOME_CALL_1170 = "call_1170"  # safe paths exhausted -> recommended the phone line

# Which lane handled the turn (BLOK 3 router).
ROUTE_CASE = "case"
ROUTE_RAG = "rag"
ROUTE_GREETING = "greeting"
ROUTE_POLICY = "policy"  # answered from matched VMQ-778 policy rules (legal basis)


@dataclass(frozen=True)
class AuditEvent:
    """One recorded assistant turn."""

    channel: str
    language: str
    outcome: str
    category: str | None = None
    tree_id: str | None = None
    card_id: str | None = None
    session_id: str | None = None
    route: str | None = None
    style: str | None = None  # explanation style in use (for style distribution)
    detail: str | None = None  # free detail, e.g. the 1170 recommendation reason
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class AuditLog(Protocol):
    """Storage-agnostic audit sink and metrics source."""

    async def record(self, event: AuditEvent) -> None: ...

    async def metrics(self) -> dict[str, object]: ...

    async def trends(self) -> dict[str, object]: ...


def _window_kpis(outcomes: Counter[str]) -> dict[str, object]:
    """The headline KPIs for one time window (reuses compute_metrics)."""
    m = compute_metrics(outcomes, Counter())
    return {
        "total_events": m["total_events"],
        "terminal_events": m["terminal_events"],
        "self_service_resolution_rate": m["self_service_resolution_rate"],
        "ai_resolution_rate": m["ai_resolution_rate"],
        "call_1170_rate": m["call_1170_rate"],
        "handoff_rate": m["handoff_rate"],
    }


def compute_trends(
    events: list[tuple[datetime, str]],
    *,
    now: datetime | None = None,
    windows: tuple[int, ...] = (7, 30, 90),
    bucket_days: int = 14,
) -> dict[str, object]:
    """Windowed KPIs plus a per-day series, to show whether quality is improving.

    ``events`` is (timestamp, outcome) pairs. For each window (last N days) the
    headline rates are computed; the daily series gives resolution and 1170 rates per
    day over the last ``bucket_days`` so a trend is visible. Empty windows yield null
    rates rather than fabricated numbers.
    """
    now = now or datetime.now(UTC)
    windows_out: dict[str, object] = {}
    for w in windows:
        cutoff = now - timedelta(days=w)
        oc: Counter[str] = Counter(o for ts, o in events if ts >= cutoff)
        windows_out[f"{w}d"] = _window_kpis(oc)

    daily: list[dict[str, object]] = []
    for offset in range(bucket_days - 1, -1, -1):
        day_start = (now - timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        oc = Counter(o for ts, o in events if day_start <= ts < day_end)
        kpis = _window_kpis(oc)
        daily.append(
            {
                "date": day_start.date().isoformat(),
                "total_events": kpis["total_events"],
                "self_service_resolution_rate": kpis["self_service_resolution_rate"],
                "call_1170_rate": kpis["call_1170_rate"],
            }
        )
    return {"generated_at": now.isoformat(), "windows": windows_out, "daily": daily}


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def compute_metrics(
    outcomes: Counter[str],
    categories: Counter[str],
    routes: Counter[str] | None = None,
    *,
    failure_cards: Counter[str] | None = None,
    styles: Counter[str] | None = None,
    call_1170_reasons: Counter[str] | None = None,
) -> dict[str, object]:
    """Derive KPI figures from outcome, category and route counts."""
    routes = routes if routes is not None else Counter()
    resolved = outcomes.get(OUTCOME_RESOLVED, 0)
    answered = outcomes.get(OUTCOME_ANSWER, 0)
    handoff = outcomes.get(OUTCOME_HANDOFF, 0)
    lc_success = outcomes.get(OUTCOME_LC_SUCCESS, 0)
    lc_failure = outcomes.get(OUTCOME_LC_FAILURE, 0)
    lc_partial = outcomes.get(OUTCOME_LC_PARTIAL, 0)
    lc_unclear = outcomes.get(OUTCOME_LC_UNCLEAR, 0)
    call_1170 = outcomes.get(OUTCOME_CALL_1170, 0)
    lc_results = lc_success + lc_failure + lc_partial + lc_unclear
    # A self-service win is a resolution card, a grounded KB answer, or a lifecycle
    # success; 1170 is a terminal non-win (never a human-chat handoff).
    wins = resolved + answered + lc_success
    terminal = wins + handoff + call_1170
    total = int(sum(outcomes.values()))
    metrics: dict[str, object] = {
        "total_events": total,
        "outcomes": dict(outcomes),
        "categories": dict(categories),
        "routes": dict(routes),
        "terminal_events": terminal,
        "resolved_events": resolved,
        "answered_events": answered,
        "handoff_events": handoff,
        "self_service_resolution_rate": _rate(wins, terminal),
        "handoff_rate": _rate(handoff, terminal),
        # Resolution-lifecycle KPIs.
        "lifecycle_results": lc_results,
        "ai_resolution_rate": _rate(lc_success, lc_success + call_1170),
        "first_result_success_rate": _rate(lc_success, lc_results),
        "unclear_outcome_rate": _rate(lc_unclear, lc_results),
        "call_1170_count": call_1170,
        "call_1170_rate": _rate(call_1170, terminal),
    }
    if failure_cards is not None:
        metrics["cards_failing_most"] = dict(failure_cards.most_common(10))
    if styles is not None:
        metrics["explanation_style_distribution"] = dict(styles)
    if call_1170_reasons is not None:
        metrics["call_1170_reasons"] = dict(call_1170_reasons)
    return metrics


class InMemoryAuditLog:
    """Process-local audit log; resets on restart. Default for tests and no-DB runs."""

    def __init__(self) -> None:
        self._outcomes: Counter[str] = Counter()
        self._categories: Counter[str] = Counter()
        self._routes: Counter[str] = Counter()
        self._failure_cards: Counter[str] = Counter()
        self._styles: Counter[str] = Counter()
        self._call_reasons: Counter[str] = Counter()
        # (timestamp, outcome) pairs for time-windowed trends; bounded so memory is
        # stable on long dev runs (the Postgres backend trends over the full table).
        self._events: list[tuple[datetime, str]] = []
        self._max_events = 50_000
        self._count = 0

    async def record(self, event: AuditEvent) -> None:
        self._events.append((event.created_at, event.outcome))
        if len(self._events) > self._max_events:
            del self._events[: len(self._events) - self._max_events]
        self._outcomes[event.outcome] += 1
        if event.category:
            self._categories[event.category] += 1
        if event.route:
            self._routes[event.route] += 1
        if event.outcome == OUTCOME_LC_FAILURE and event.card_id:
            self._failure_cards[event.card_id] += 1
        if event.style:
            self._styles[event.style] += 1
        if event.outcome == OUTCOME_CALL_1170 and event.detail:
            self._call_reasons[event.detail] += 1
        self._count += 1

    async def metrics(self) -> dict[str, object]:
        return compute_metrics(
            self._outcomes,
            self._categories,
            self._routes,
            failure_cards=self._failure_cards,
            styles=self._styles,
            call_1170_reasons=self._call_reasons,
        )

    async def trends(self) -> dict[str, object]:
        return compute_trends(self._events)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    language TEXT NOT NULL,
    outcome TEXT NOT NULL,
    category TEXT,
    tree_id TEXT,
    card_id TEXT,
    session_id TEXT,
    route TEXT,
    style TEXT,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# Add columns on databases created before these columns existed.
_MIGRATE_ROUTE_SQL = "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS route TEXT"
_MIGRATE_STYLE_SQL = "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS style TEXT"
_MIGRATE_DETAIL_SQL = "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS detail TEXT"

_INSERT_SQL = """
INSERT INTO audit_events
    (channel, language, outcome, category, tree_id, card_id, session_id, route,
     style, detail, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
"""


class PostgresAuditLog:
    """Durable audit log backed by PostgreSQL (asyncpg). Survives restarts."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, dsn: str) -> PostgresAuditLog:
        """Open a pool and ensure the table exists (a minimal first migration)."""
        import asyncpg  # imported lazily so the app runs without a database

        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        async with pool.acquire() as connection:
            await connection.execute(_CREATE_TABLE_SQL)
            await connection.execute(_MIGRATE_ROUTE_SQL)
            await connection.execute(_MIGRATE_STYLE_SQL)
            await connection.execute(_MIGRATE_DETAIL_SQL)
        return cls(pool)

    async def record(self, event: AuditEvent) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                _INSERT_SQL,
                event.channel,
                event.language,
                event.outcome,
                event.category,
                event.tree_id,
                event.card_id,
                event.session_id,
                event.route,
                event.style,
                event.detail,
                event.created_at,
            )

    async def metrics(self) -> dict[str, object]:
        async with self._pool.acquire() as connection:
            outcome_rows = await connection.fetch(
                "SELECT outcome, count(*) AS n FROM audit_events GROUP BY outcome"
            )
            category_rows = await connection.fetch(
                "SELECT category, count(*) AS n FROM audit_events "
                "WHERE category IS NOT NULL GROUP BY category"
            )
            route_rows = await connection.fetch(
                "SELECT route, count(*) AS n FROM audit_events "
                "WHERE route IS NOT NULL GROUP BY route"
            )
            failure_rows = await connection.fetch(
                "SELECT card_id, count(*) AS n FROM audit_events "
                "WHERE outcome = $1 AND card_id IS NOT NULL GROUP BY card_id",
                OUTCOME_LC_FAILURE,
            )
            style_rows = await connection.fetch(
                "SELECT style, count(*) AS n FROM audit_events "
                "WHERE style IS NOT NULL GROUP BY style"
            )
            reason_rows = await connection.fetch(
                "SELECT detail, count(*) AS n FROM audit_events "
                "WHERE outcome = $1 AND detail IS NOT NULL GROUP BY detail",
                OUTCOME_CALL_1170,
            )
        outcomes: Counter[str] = Counter({row["outcome"]: int(row["n"]) for row in outcome_rows})
        categories: Counter[str] = Counter(
            {row["category"]: int(row["n"]) for row in category_rows}
        )
        routes: Counter[str] = Counter({row["route"]: int(row["n"]) for row in route_rows})
        failure_cards: Counter[str] = Counter(
            {row["card_id"]: int(row["n"]) for row in failure_rows}
        )
        styles: Counter[str] = Counter({row["style"]: int(row["n"]) for row in style_rows})
        reasons: Counter[str] = Counter({row["detail"]: int(row["n"]) for row in reason_rows})
        return compute_metrics(
            outcomes,
            categories,
            routes,
            failure_cards=failure_cards,
            styles=styles,
            call_1170_reasons=reasons,
        )

    async def trends(self) -> dict[str, object]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT created_at, outcome FROM audit_events "
                "WHERE created_at >= now() - interval '90 days'"
            )
        events = [(row["created_at"], row["outcome"]) for row in rows]
        return compute_trends(events)

    async def close(self) -> None:
        await self._pool.close()
