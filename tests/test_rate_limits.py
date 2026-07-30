"""Independent request-rate protection."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.schemas import LLMRequest, LLMResult
from app.main import create_app


class CountingProvider:
    """Prove rate rejection occurs before provider generation."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        return LLMResult(text=request.passages[0], citations=[request.source_ids[0]])


def test_requests_above_rate_are_rejected_with_retry_after() -> None:
    provider = CountingProvider()
    settings = Settings(
        llm_generation_limit_per_session=10,
        request_rate_limit_per_minute=2,
    )
    with TestClient(create_app(settings=settings, provider=provider)) as client:
        first = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Give me a recipe"},
        )
        session_id = first.json()["session_id"]
        second = client.post(
            "/api/v1/chat",
            json={"session_id": session_id, "message": "Give me a recipe"},
        )
        third = client.post(
            "/api/v1/chat",
            json={"session_id": session_id, "message": "Show the IMEI demo fixture"},
        )

    assert first.status_code == second.status_code == 200
    assert third.status_code == 429
    assert third.headers["Retry-After"] == "60"
    assert third.json()["response_type"] == "rate_limited"
    assert third.json()["retry_after_seconds"] == 60
    assert provider.calls == 0


def test_rate_counters_are_isolated_between_sessions() -> None:
    settings = Settings(request_rate_limit_per_minute=1)
    with TestClient(create_app(settings=settings)) as client:
        first = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Give me a recipe"},
        )
        second_session = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Give me a recipe"},
        )
        first_limited = client.post(
            "/api/v1/chat",
            json={
                "session_id": first.json()["session_id"],
                "message": "Give me a recipe",
            },
        )

    assert second_session.status_code == 200
    assert first_limited.status_code == 429
