"""End-to-end source authorization around provider output."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.schemas import LLMRequest, LLMResult
from app.main import create_app


class FabricatedCitationProvider:
    """Attempt to cite a source not supplied by retrieval."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        return LLMResult(
            text=request.passages[0],
            citations=["FABRICATED-SOURCE-ID"],
        )


class MissingCitationProvider:
    """Return text without the required machine-readable citation."""

    async def generate(self, request: LLMRequest) -> LLMResult:
        return LLMResult(text=request.passages[0], citations=[])


class RecordingProvider:
    """Record the exact minimum context supplied by the application."""

    def __init__(self) -> None:
        self.request: LLMRequest | None = None

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.request = request
        return LLMResult(
            text=request.passages[0],
            citations=[request.source_ids[0]],
        )


def test_fabricated_provider_citation_is_rejected() -> None:
    with TestClient(create_app(provider=FabricatedCitationProvider())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Show the IMEI demo fixture"},
        )

    body = response.json()
    assert body["grounded"] is False
    assert body["sources"] == []
    assert body["handoff_reason"] == "output_validation_failed"
    assert "FABRICATED-SOURCE-ID" not in response.text


def test_missing_provider_citation_is_rejected() -> None:
    with TestClient(create_app(provider=MissingCitationProvider())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Show the IMEI demo fixture"},
        )

    assert response.json()["handoff_reason"] == "output_validation_failed"
    assert response.json()["sources"] == []


def test_only_retrieved_context_reaches_provider_and_public_sources() -> None:
    provider = RecordingProvider()
    with TestClient(create_app(provider=provider)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Show the IMEI demo fixture"},
        )

    assert provider.request is not None
    assert provider.request.source_ids == ["DEMO-EN-IMEI-001"]
    assert len(provider.request.passages) == 1
    assert response.json()["sources"] == [
        {
            "document_id": "DEMO-EN-IMEI-001",
            "title": "Demo IMEI fixture — not approved for production",
            "url": None,
            "version": "demo-1",
            "demo_only": True,
        }
    ]
