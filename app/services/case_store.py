"""Server-side storage for the evolving CaseState, keyed by session.

The diagnose flow stays stateless (the client carries tree/node); the case
reasoning layer needs continuity, so it keeps one CaseState per session id here.
The default is process-local and resets on restart; a Postgres backend behind the
same async protocol survives restarts, so a conversation is not lost mid-case when
the server is redeployed.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from app.domain.case_state import CaseState


def _new_case(session_id: str, *, language: str, channel: str) -> CaseState:
    return CaseState(
        case_id=uuid4().hex[:12],
        session_id=session_id,
        language=language,
        channel=channel,
    )


@runtime_checkable
class CaseStore(Protocol):
    """Storage boundary for per-session case reasoning state."""

    async def get(self, session_id: str) -> CaseState | None: ...

    async def get_or_create(self, session_id: str, *, language: str, channel: str) -> CaseState: ...

    async def save(self, case: CaseState) -> None: ...

    async def reset(self, session_id: str) -> None: ...


class InMemoryCaseStore:
    """Process-local case store; resets on restart. Default for tests and dev."""

    def __init__(self) -> None:
        self._cases: dict[str, CaseState] = {}

    async def get(self, session_id: str) -> CaseState | None:
        return self._cases.get(session_id)

    async def get_or_create(self, session_id: str, *, language: str, channel: str) -> CaseState:
        existing = self._cases.get(session_id)
        if existing is not None:
            return existing
        case = _new_case(session_id, language=language, channel=channel)
        self._cases[session_id] = case
        return case

    async def save(self, case: CaseState) -> None:
        self._cases[case.session_id] = case

    async def reset(self, session_id: str) -> None:
        self._cases.pop(session_id, None)


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS case_state (
    session_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_UPSERT_SQL = """
INSERT INTO case_state (session_id, data, updated_at)
VALUES ($1, $2, now())
ON CONFLICT (session_id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
"""


class PostgresCaseStore:
    """Durable case store backed by PostgreSQL (asyncpg). Survives restarts."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, dsn: str) -> PostgresCaseStore:
        """Open a pool and ensure the table exists (a minimal first migration)."""
        import asyncpg  # imported lazily so the app runs without a database

        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        async with pool.acquire() as connection:
            await connection.execute(_CREATE_TABLE_SQL)
        return cls(pool)

    async def get(self, session_id: str) -> CaseState | None:
        async with self._pool.acquire() as connection:
            data = await connection.fetchval(
                "SELECT data FROM case_state WHERE session_id = $1", session_id
            )
        return CaseState.model_validate_json(data) if data is not None else None

    async def get_or_create(self, session_id: str, *, language: str, channel: str) -> CaseState:
        existing = await self.get(session_id)
        if existing is not None:
            return existing
        case = _new_case(session_id, language=language, channel=channel)
        await self.save(case)
        return case

    async def save(self, case: CaseState) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(_UPSERT_SQL, case.session_id, case.model_dump_json())

    async def reset(self, session_id: str) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute("DELETE FROM case_state WHERE session_id = $1", session_id)

    async def close(self) -> None:
        await self._pool.close()
