"""Provider protocol kept intentionally small for Demo 1."""

from typing import Protocol

from app.domain.schemas import LLMRequest, LLMResult


class LLMProvider(Protocol):
    """Natural-language provider that has no workflow authorization powers."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        """Generate text from already-approved passages."""
        ...
