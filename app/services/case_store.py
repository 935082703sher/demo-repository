"""Server-side storage for the evolving CaseState, keyed by session.

The diagnose flow stays stateless (the client carries tree/node); the case
reasoning layer needs continuity, so it keeps one CaseState per session id here.
The default is process-local; a Redis/Postgres backend can replace it behind the
same protocol without touching callers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import uuid4

from app.domain.case_state import CaseState


@runtime_checkable
class CaseStore(Protocol):
    """Storage boundary for per-session case reasoning state."""

    def get(self, session_id: str) -> CaseState | None: ...

    def get_or_create(self, session_id: str, *, language: str, channel: str) -> CaseState: ...

    def save(self, case: CaseState) -> None: ...

    def reset(self, session_id: str) -> None: ...


class InMemoryCaseStore:
    """Process-local case store; resets on restart. Default for tests and dev."""

    def __init__(self) -> None:
        self._cases: dict[str, CaseState] = {}

    def get(self, session_id: str) -> CaseState | None:
        return self._cases.get(session_id)

    def get_or_create(self, session_id: str, *, language: str, channel: str) -> CaseState:
        existing = self._cases.get(session_id)
        if existing is not None:
            return existing
        case = CaseState(
            case_id=uuid4().hex[:12],
            session_id=session_id,
            language=language,
            channel=channel,
        )
        self._cases[session_id] = case
        return case

    def save(self, case: CaseState) -> None:
        self._cases[case.session_id] = case

    def reset(self, session_id: str) -> None:
        self._cases.pop(session_id, None)
