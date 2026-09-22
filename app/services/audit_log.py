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
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

# Terminal and intermediate outcomes of one assistant turn.
OUTCOME_RESOLVED = "resolved"  # a resolution card was returned (self-service win)
OUTCOME_HANDOFF = "handoff"  # escalated to a human
OUTCOME_QUESTION = "question"  # a diagnostic question was asked (in progress)
OUTCOME_CLARIFY = "clarify"  # a routing menu was offered


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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class AuditLog(Protocol):
    """Storage-agnostic audit sink and metrics source."""

    async def record(self, event: AuditEvent) -> None: ...

    async def metrics(self) -> dict[str, object]: ...


def compute_metrics(outcomes: Counter[str], categories: Counter[str]) -> dict[str, object]:
    """Derive KPI figures from outcome and category counts."""
    resolved = outcomes.get(OUTCOME_RESOLVED, 0)
    handoff = outcomes.get(OUTCOME_HANDOFF, 0)
    terminal = resolved + handoff
    total = int(sum(outcomes.values()))
    return {
        "total_events": total,
        "outcomes": dict(outcomes),
        "categories": dict(categories),
        "terminal_events": terminal,
        # Self-service resolution rate: resolved out of terminal (resolved+handoff).
        "self_service_resolution_rate": round(resolved / terminal, 4) if terminal else None,
        "handoff_rate": round(handoff / terminal, 4) if terminal else None,
    }


class InMemoryAuditLog:
    """Process-local audit log; resets on restart. Default for tests and no-DB runs."""

    def __init__(self) -> None:
        self._outcomes: Counter[str] = Counter()
        self._categories: Counter[str] = Counter()
        self._count = 0

    async def record(self, event: AuditEvent) -> None:
        self._outcomes[event.outcome] += 1
        if event.category:
            self._categories[event.category] += 1
        self._count += 1

    async def metrics(self) -> dict[str, object]:
        return compute_metrics(self._outcomes, self._categories)


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
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_INSERT_SQL = """
INSERT INTO audit_events
    (channel, language, outcome, category, tree_id, card_id, session_id, created_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
        outcomes: Counter[str] = Counter({row["outcome"]: int(row["n"]) for row in outcome_rows})
        categories: Counter[str] = Counter(
            {row["category"]: int(row["n"]) for row in category_rows}
        )
        return compute_metrics(outcomes, categories)

    async def close(self) -> None:
        await self._pool.close()
