"""Deterministic provider used by local runs and automated tests."""

from app.domain.schemas import LLMRequest, LLMResult


class MockLLMProvider:
    """Return the supplied demo passage verbatim; never use model memory."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        """Produce a stable grounded response without network access."""
        if not request.passages:
            raise ValueError("Mock provider requires approved context")
        return LLMResult(text=request.passages[0])
