"""Business services for independent quota and request-rate controls."""

from __future__ import annotations

from uuid import UUID

from app.domain.usage import RateLimitDecision, UsageAuthorization, UsageSnapshot
from app.repositories.usage_repository import RateLimitRepository, UsageRepository


class UsageLimitService:
    """Apply configured logical-generation allowance to server-owned state."""

    def __init__(self, repository: UsageRepository, *, limit: int, window_seconds: int) -> None:
        self._repository = repository
        self._limit = limit
        self._window_seconds = window_seconds

    @property
    def limit(self) -> int:
        """Configured logical generation limit."""
        return self._limit

    def authorize(self, session_id: UUID) -> UsageAuthorization:
        """Atomically authorize one logical external generation."""
        return self._repository.authorize(
            session_id,
            limit=self._limit,
            window_seconds=self._window_seconds,
        )

    def record_attempt(self, session_id: UUID) -> None:
        """Record an actual provider attempt."""
        self._repository.record_provider_attempt(session_id)

    def record_result(
        self,
        session_id: UUID,
        *,
        success: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: float = 0.0,
        latency_ms: float = 0.0,
    ) -> None:
        """Record one logical generation outcome and measurements."""
        self._repository.record_generation_result(
            session_id,
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
            latency_ms=latency_ms,
        )

    def snapshot(self, session_id: UUID) -> UsageSnapshot:
        """Return current usage for tests and internal measurement."""
        return self._repository.snapshot(
            session_id,
            limit=self._limit,
            window_seconds=self._window_seconds,
        )


class RequestRateLimitService:
    """Apply the independent per-session request-rate policy."""

    def __init__(self, repository: RateLimitRepository, *, limit: int) -> None:
        self._repository = repository
        self._limit = limit

    @property
    def limit(self) -> int:
        """Configured requests-per-minute limit."""
        return self._limit

    def check(self, session_id: UUID) -> RateLimitDecision:
        """Authorize and record one valid chat request."""
        return self._repository.check_and_record(session_id, limit=self._limit)
