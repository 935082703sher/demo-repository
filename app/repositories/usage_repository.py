"""Thread-safe in-memory quota and rate-limit repositories."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Protocol
from uuid import UUID

from app.domain.usage import RateLimitDecision, UsageAuthorization, UsageSnapshot


class UsageRepository(Protocol):
    """Storage boundary for logical LLM usage."""

    def authorize(
        self,
        session_id: UUID,
        *,
        limit: int,
        window_seconds: int,
    ) -> UsageAuthorization:
        """Atomically authorize and count one logical generation."""
        ...

    def record_provider_attempt(self, session_id: UUID) -> None:
        """Record one actual provider call, including retries."""
        ...

    def record_generation_result(
        self,
        session_id: UUID,
        *,
        success: bool,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        latency_ms: float,
    ) -> None:
        """Record the final result of one logical generation."""
        ...

    def snapshot(self, session_id: UUID, *, limit: int, window_seconds: int) -> UsageSnapshot:
        """Return current server-owned counters."""
        ...


class RateLimitRepository(Protocol):
    """Storage boundary for request-rate protection."""

    def check_and_record(self, session_id: UUID, *, limit: int) -> RateLimitDecision:
        """Atomically allow or reject one request in the current minute."""
        ...


@dataclass(slots=True)
class _UsageWindow:
    started_at: datetime
    logical_requests: int = 0
    provider_attempts: int = 0
    successful_generations: int = 0
    failed_generations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: float = 0.0


class InMemoryUsageRepository:
    """Process-local usage storage; state intentionally disappears on restart."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._windows: dict[UUID, _UsageWindow] = {}
        self._lock = RLock()

    def authorize(
        self,
        session_id: UUID,
        *,
        limit: int,
        window_seconds: int,
    ) -> UsageAuthorization:
        """Atomically consume at most one logical allowance unit."""
        with self._lock:
            window = self._active_window(session_id, window_seconds)
            if window.logical_requests >= limit:
                return UsageAuthorization(
                    allowed=False,
                    snapshot=self._snapshot(window, limit, window_seconds),
                )
            window.logical_requests += 1
            return UsageAuthorization(
                allowed=True,
                snapshot=self._snapshot(window, limit, window_seconds),
            )

    def record_provider_attempt(self, session_id: UUID) -> None:
        """Count an actual provider attempt separately from logical allowance."""
        with self._lock:
            self._windows[session_id].provider_attempts += 1

    def record_generation_result(
        self,
        session_id: UUID,
        *,
        success: bool,
        input_tokens: int,
        output_tokens: int,
        estimated_cost: float,
        latency_ms: float,
    ) -> None:
        """Accumulate final provider measurements without message content."""
        with self._lock:
            window = self._windows[session_id]
            if success:
                window.successful_generations += 1
            else:
                window.failed_generations += 1
            window.input_tokens += input_tokens
            window.output_tokens += output_tokens
            window.estimated_cost += estimated_cost
            window.latency_ms += latency_ms

    def snapshot(self, session_id: UUID, *, limit: int, window_seconds: int) -> UsageSnapshot:
        """Return a defensive immutable view, creating an empty active window if needed."""
        with self._lock:
            return self._snapshot(
                self._active_window(session_id, window_seconds),
                limit,
                window_seconds,
            )

    def _active_window(self, session_id: UUID, window_seconds: int) -> _UsageWindow:
        now = self._clock()
        window = self._windows.get(session_id)
        if window is None or now >= window.started_at + timedelta(seconds=window_seconds):
            window = _UsageWindow(started_at=now)
            self._windows[session_id] = window
        return window

    @staticmethod
    def _snapshot(window: _UsageWindow, limit: int, window_seconds: int) -> UsageSnapshot:
        return UsageSnapshot(
            logical_requests=window.logical_requests,
            provider_attempts=window.provider_attempts,
            successful_generations=window.successful_generations,
            failed_generations=window.failed_generations,
            input_tokens=window.input_tokens,
            output_tokens=window.output_tokens,
            estimated_cost=window.estimated_cost,
            latency_ms=window.latency_ms,
            remaining=max(0, limit - window.logical_requests),
            reset_at=window.started_at + timedelta(seconds=window_seconds),
        )


class InMemoryRateLimitRepository:
    """Sliding-minute request limiter isolated by server-generated session ID."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._requests: dict[UUID, deque[datetime]] = {}
        self._lock = RLock()

    def check_and_record(self, session_id: UUID, *, limit: int) -> RateLimitDecision:
        """Record an allowed request or return the safe retry interval."""
        now = self._clock()
        cutoff = now - timedelta(seconds=60)
        with self._lock:
            requests = self._requests.setdefault(session_id, deque())
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= limit:
                retry = max(
                    1,
                    math.ceil((requests[0] + timedelta(seconds=60) - now).total_seconds()),
                )
                return RateLimitDecision(False, 0, retry)
            requests.append(now)
            return RateLimitDecision(True, limit - len(requests), None)
