"""Bounded provider execution and usage measurement."""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

from app.domain.schemas import LLMRequest, LLMResult
from app.providers.base import LLMProvider
from app.providers.errors import ProviderError, ProviderOutputError, ProviderUnavailableError
from app.services.usage_limits import UsageLimitService


class GroundedGenerationService:
    """Execute one logical generation with bounded retries and measurements."""

    def __init__(
        self,
        provider: LLMProvider,
        usage_limits: UsageLimitService,
        *,
        timeout_seconds: float,
        max_retries: int,
        input_cost_per_million: float,
        output_cost_per_million: float,
    ) -> None:
        self._provider = provider
        self._usage_limits = usage_limits
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._input_cost_per_million = input_cost_per_million
        self._output_cost_per_million = output_cost_per_million

    async def generate(self, session_id: UUID, request: LLMRequest) -> LLMResult:
        """Count retries as attempts while preserving one logical quota unit."""
        started = time.perf_counter()
        final_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._usage_limits.record_attempt(session_id)
            try:
                result = await asyncio.wait_for(
                    self._provider.generate(request),
                    timeout=self._timeout_seconds,
                )
                if not isinstance(result, LLMResult):
                    raise ProviderOutputError("provider result type was invalid")
                latency_ms = (time.perf_counter() - started) * 1000
                self._usage_limits.record_result(
                    session_id,
                    success=True,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    estimated_cost=self._estimated_cost(result),
                    latency_ms=latency_ms,
                )
                return result
            except TimeoutError as exc:
                final_error = ProviderUnavailableError("provider request timed out")
                final_error.__cause__ = exc
            except ProviderError as exc:
                final_error = exc
                if not exc.retryable:
                    break
            except Exception as exc:
                final_error = ProviderUnavailableError("provider request unavailable")
                final_error.__cause__ = exc
            if attempt >= self._max_retries:
                break

        self._usage_limits.record_result(
            session_id,
            success=False,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        raise final_error or ProviderUnavailableError("provider request unavailable")

    def _estimated_cost(self, result: LLMResult) -> float:
        return (
            result.input_tokens * self._input_cost_per_million
            + result.output_tokens * self._output_cost_per_million
        ) / 1_000_000
