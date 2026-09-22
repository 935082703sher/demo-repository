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
from typing import Protocol, runtime_checkable

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
