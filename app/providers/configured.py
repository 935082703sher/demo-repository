"""Configuration-selected provider construction."""

from app.core.config import Settings
from app.domain.schemas import LLMRequest, LLMResult
from app.providers.base import LLMProvider
from app.providers.errors import ProviderConfigurationError
from app.providers.mock_llm import MockLLMProvider
from app.providers.openai_responses import OpenAIResponsesProvider


class UnavailableConfiguredProvider:
    """Fail safely when a selected external provider lacks configuration."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        """Return no generated content and expose no configuration detail."""
        raise ProviderConfigurationError("configured provider is unavailable")


def build_configured_provider(settings: Settings) -> LLMProvider:
    """Select the provider without activating a paid service by default."""
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    api_key = settings.llm_api_key
    if api_key is None or not api_key.get_secret_value() or not settings.llm_model:
        return UnavailableConfiguredProvider()
    return OpenAIResponsesProvider(
        api_key=api_key.get_secret_value(),
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
    )
