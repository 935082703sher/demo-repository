"""Configured provider, structured output, retry, and measurement tests."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.enums import Category, Language
from app.domain.schemas import LLMRequest, LLMResult
from app.main import create_app
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderOutputError,
    ProviderUnavailableError,
)
from app.providers.openai_responses import OpenAIResponsesProvider
from app.repositories.usage_repository import InMemoryUsageRepository
from app.services.generation import GroundedGenerationService
from app.services.usage_limits import UsageLimitService


def grounded_request() -> LLMRequest:
    """Create minimum synthetic context for provider tests."""
    return LLMRequest(
        language=Language.EN,
        question="Question from citizen@example.invalid about 998 90 123 45 67",
        category=Category.IMEI,
        source_ids=["TEST-SOURCE-001"],
        passages=["Synthetic approved test passage."],
    )


@pytest.mark.anyio
async def test_openai_adapter_uses_structured_minimum_context() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["authorization"] = request.headers["Authorization"]
        observed["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "answer": "Synthetic grounded answer.",
                                        "citations": ["TEST-SOURCE-001"],
                                    }
                                ),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 5},
            },
        )

    provider = OpenAIResponsesProvider(
        api_key="test-secret-key",
        model="test-model",
        timeout_seconds=1,
        max_output_tokens=100,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate(grounded_request())

    assert result.text == "Synthetic grounded answer."
    assert result.citations == ["TEST-SOURCE-001"]
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert result.provider_name == "openai"
    body = str(observed["body"])
    assert "TEST-SOURCE-001" in body
    assert "Synthetic approved test passage." in body
    assert "citizen@example.invalid" not in body
    assert "998 90 123 45 67" not in body
    assert observed["authorization"] == "Bearer test-secret-key"


@pytest.mark.anyio
async def test_malformed_structured_output_is_rejected() -> None:
    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="test-model",
        timeout_seconds=1,
        max_output_tokens=100,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "not-json"}],
                        }
                    ]
                },
            )
        ),
    )

    with pytest.raises(ProviderOutputError):
        await provider.generate(grounded_request())


@pytest.mark.anyio
async def test_authentication_failure_does_not_expose_key() -> None:
    secret = "never-expose-this-key"
    provider = OpenAIResponsesProvider(
        api_key=secret,
        model="test-model",
        timeout_seconds=1,
        max_output_tokens=100,
        transport=httpx.MockTransport(lambda _: httpx.Response(401, json={"error": "no"})),
    )

    with pytest.raises(ProviderAuthenticationError) as captured:
        await provider.generate(grounded_request())

    assert secret not in str(captured.value)


class RetryProvider:
    """Fail once, then return measured synthetic output."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        if self.calls == 1:
            raise ProviderUnavailableError("temporary")
        return LLMResult(
            text=request.passages[0],
            citations=[request.source_ids[0]],
            input_tokens=10,
            output_tokens=5,
            provider_name="fake",
            model_name="fake-model",
        )


@pytest.mark.anyio
async def test_retry_is_one_logical_allowance_but_two_attempts() -> None:
    repository = InMemoryUsageRepository()
    usage = UsageLimitService(repository, limit=1, window_seconds=60)
    provider = RetryProvider()
    generation = GroundedGenerationService(
        provider,
        usage,
        timeout_seconds=1,
        max_retries=1,
        input_cost_per_million=2,
        output_cost_per_million=4,
    )
    session_id = uuid4()
    assert usage.authorize(session_id).allowed

    result = await generation.generate(session_id, grounded_request())
    snapshot = usage.snapshot(session_id)

    assert result.citations == ["TEST-SOURCE-001"]
    assert snapshot.logical_requests == 1
    assert snapshot.provider_attempts == 2
    assert snapshot.successful_generations == 1
    assert snapshot.failed_generations == 0
    assert snapshot.input_tokens == 10
    assert snapshot.output_tokens == 5
    assert snapshot.estimated_cost == pytest.approx(0.00004)


class SlowProvider:
    """Exceed the configured timeout on every attempt."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        await asyncio.sleep(0.05)
        return LLMResult(text=request.passages[0])


@pytest.mark.anyio
async def test_timeout_retries_are_bounded_and_fail_safely() -> None:
    repository = InMemoryUsageRepository()
    usage = UsageLimitService(repository, limit=1, window_seconds=60)
    generation = GroundedGenerationService(
        SlowProvider(),
        usage,
        timeout_seconds=0.001,
        max_retries=1,
        input_cost_per_million=0,
        output_cost_per_million=0,
    )
    session_id = uuid4()
    assert usage.authorize(session_id).allowed

    with pytest.raises(ProviderUnavailableError):
        await generation.generate(session_id, grounded_request())

    snapshot = usage.snapshot(session_id)
    assert snapshot.logical_requests == 1
    assert snapshot.provider_attempts == 2
    assert snapshot.failed_generations == 1


def test_selected_provider_without_configuration_fails_as_handoff() -> None:
    settings = Settings(llm_provider="openai", llm_model="", llm_api_key=None)
    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Show the IMEI demo fixture"},
        )

    assert response.status_code == 200
    assert response.json()["handoff_reason"] == "provider_unavailable"


def test_api_key_is_redacted_from_settings_representation() -> None:
    secret = "settings-secret-must-not-appear"
    settings = Settings(llm_api_key=secret)

    assert secret not in repr(settings)
    assert "**********" in repr(settings)
