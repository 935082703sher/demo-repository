"""Deterministic scope and localized refusal coverage."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.schemas import LLMRequest, LLMResult
from app.main import create_app
from app.services.scope import ScopeService, ScopeStatus


class CountingProvider:
    """Provider double proving that clear refusals never generate."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        return LLMResult(text=request.passages[0], citations=[request.source_ids[0]])


def test_clear_out_of_scope_topics_are_detected() -> None:
    service = ScopeService()
    messages = (
        "Plan a travel itinerary",
        "Explain a religious teaching",
        "Predict the political election",
        "Recommend a movie",
        "Do my homework",
        "Give me a recipe",
        "Give general medical advice",
        "Write Python code",
        "What is the capital of France?",
    )

    assert all(service.classify(message).status is ScopeStatus.OUT_OF_SCOPE for message in messages)


def test_legitimate_telecommunications_request_is_in_scope() -> None:
    decision = ScopeService().classify("My mobile network signal is weak")

    assert decision.status is ScopeStatus.IN_SCOPE


def test_ambiguous_request_remains_ambiguous() -> None:
    assert ScopeService().classify("Please help me").status is ScopeStatus.AMBIGUOUS


def test_out_of_scope_refusal_is_localized_and_skips_provider() -> None:
    provider = CountingProvider()
    cases = (
        ("uz", "Menga sayohat rejasini tuzing", "Men RTMCning"),
        ("ru", "Дайте рецепт супа", "Я — ИИ-помощник RTMC"),
        ("en", "Recommend a movie", "I’m the RTMC"),
    )

    with TestClient(create_app(provider=provider)) as client:
        for language, message, expected in cases:
            response = client.post(
                "/api/v1/chat",
                json={"language": language, "message": message},
            )
            body = response.json()
            assert response.status_code == 200
            assert body["language"] == language
            assert body["response_type"] == "refusal"
            assert body["safety_flags"] == ["out_of_scope"]
            assert expected in body["reply"]

    assert provider.calls == 0


def test_language_selection_precedes_scope_refusal() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/chat", json={"message": "Give me a recipe"})

    assert response.json()["response_type"] == "language_selection"
    assert response.json()["language"] is None
