"""Self-hosted Ollama provider tests. No real network or Ollama server required."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.enums import Category, Language
from app.domain.schemas import LLMRequest
from app.main import create_app
from app.providers.configured import UnavailableConfiguredProvider, build_configured_provider
from app.providers.errors import ProviderOutputError, ProviderUnavailableError
from app.providers.ollama import OllamaProvider


def grounded_request(question: str = "Show the IMEI demo fixture") -> LLMRequest:
    """Create minimum synthetic context for provider tests."""
    return LLMRequest(
        language=Language.EN,
        question=question,
        category=Category.IMEI,
        source_ids=["TEST-SOURCE-001"],
        passages=["Synthetic approved test passage."],
    )


def _ollama_envelope(answer: str, citations: list[str]) -> dict[str, object]:
    return {
        "model": "qwen3:8b",
        "message": {
            "role": "assistant",
            "content": json.dumps({"answer": answer, "citations": citations}),
        },
        "done": True,
        "prompt_eval_count": 42,
        "eval_count": 17,
    }


@pytest.mark.anyio
async def test_ollama_adapter_returns_grounded_answer() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_ollama_envelope("Synthetic answer.", ["TEST-SOURCE-001"]))

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate(grounded_request())

    assert result.text == "Synthetic answer."
    assert result.citations == ["TEST-SOURCE-001"]
    assert result.provider_name == "ollama"
    assert result.model_name == "qwen3:8b"
    assert result.input_tokens == 42
    assert result.output_tokens == 17
    assert observed["url"] == "http://127.0.0.1:11434/api/chat"
    body = observed["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen3:8b"
    assert body["stream"] is False
    assert body["think"] is False
    assert body["format"]["required"] == ["answer", "citations"]


@pytest.mark.anyio
async def test_ollama_adapter_supports_unicode_uzbek() -> None:
    answer = "IMEI ro'yxatdan o'tkazish uchun tasdiqlangan manba topilmadi."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ollama_envelope(answer, ["TEST-SOURCE-001"]))

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate(
        grounded_request("IMEI ro'yxatdan o'tkazish haqida ma'lumot bering")
    )

    assert result.text == answer


@pytest.mark.anyio
async def test_ollama_adapter_supports_unicode_russian() -> None:
    answer = "Информация не подтверждена утверждёнными источниками RTMC."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ollama_envelope(answer, ["TEST-SOURCE-001"]))

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate(grounded_request("Покажи IMEI демо источник"))

    assert result.text == answer


@pytest.mark.anyio
async def test_ollama_adapter_removes_defined_pii_from_question() -> None:
    sensitive_values = ("synthetic.person@example.test", "+998 90 123 45 67")
    question = "Contact me at synthetic.person@example.test or +998 90 123 45 67"
    observed_body = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_body
        observed_body = request.content.decode()
        return httpx.Response(200, json=_ollama_envelope("ok", ["TEST-SOURCE-001"]))

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    await provider.generate(grounded_request(question))

    assert all(value not in observed_body for value in sensitive_values)


@pytest.mark.anyio
async def test_ollama_adapter_raises_on_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderUnavailableError):
        await provider.generate(grounded_request())


@pytest.mark.anyio
async def test_ollama_adapter_raises_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderUnavailableError):
        await provider.generate(grounded_request())


@pytest.mark.anyio
async def test_ollama_adapter_raises_when_model_not_pulled() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="not-pulled-model",
        timeout_seconds=5,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(404, json={"error": "model not found"})
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        await provider.generate(grounded_request())


@pytest.mark.anyio
async def test_ollama_adapter_rejects_non_json_content() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": "not-json"}},
            )
        ),
    )

    with pytest.raises(ProviderOutputError):
        await provider.generate(grounded_request())


@pytest.mark.anyio
async def test_ollama_adapter_rejects_empty_content() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=_ollama_envelope("", ["TEST-SOURCE-001"]))
        ),
    )

    with pytest.raises(ProviderOutputError):
        await provider.generate(grounded_request())


@pytest.mark.anyio
async def test_ollama_adapter_rejects_missing_message_field() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"done": True})),
    )

    with pytest.raises(ProviderOutputError):
        await provider.generate(grounded_request())


@pytest.mark.anyio
async def test_ollama_adapter_raises_on_server_error() -> None:
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        model="qwen3:8b",
        timeout_seconds=5,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500, json={"error": "internal error"})
        ),
    )

    with pytest.raises(ProviderUnavailableError):
        await provider.generate(grounded_request())


def test_ollama_is_selected_by_configuration() -> None:
    settings = Settings(
        llm_provider="ollama",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="qwen3:8b",
    )

    provider = build_configured_provider(settings)

    assert isinstance(provider, OllamaProvider)


def test_ollama_without_model_fails_safe_not_crash() -> None:
    settings = Settings(llm_provider="ollama", ollama_model="")

    provider = build_configured_provider(settings)

    assert isinstance(provider, UnavailableConfiguredProvider)


def test_ollama_base_url_must_be_http() -> None:
    with pytest.raises(ValueError, match="http"):
        Settings(llm_provider="ollama", ollama_base_url="ftp://example.invalid")


def test_chat_endpoint_handles_ollama_unavailable_without_crashing() -> None:
    """The whole app must stay up and hand off safely if the local model is down."""
    settings = Settings(
        llm_provider="ollama",
        ollama_base_url="http://127.0.0.1:1",
        ollama_model="qwen3:8b",
        ollama_timeout_seconds=1,
    )
    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Show the IMEI demo fixture"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["requires_human"] is True
    assert body["handoff_reason"] == "provider_unavailable"
