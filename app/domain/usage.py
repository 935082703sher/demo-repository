"""Typed server-owned usage decisions for Demo 2."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Current LLM usage window for one session."""

    logical_requests: int
    provider_attempts: int
    successful_generations: int
    failed_generations: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    latency_ms: float
    remaining: int
    reset_at: datetime


@dataclass(frozen=True, slots=True)
class UsageAuthorization:
    """Atomic logical-generation quota decision."""

    allowed: bool
    snapshot: UsageSnapshot


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Request-rate decision independent of LLM quota."""

    allowed: bool
    remaining: int
    retry_after_seconds: int | None
