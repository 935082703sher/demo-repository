"""Local website-integration CORS configuration tests."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_cors_allows_configured_local_origin() -> None:
    settings = Settings(llm_provider="mock")
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_omits_header_for_unlisted_origin() -> None:
    settings = Settings(llm_provider="mock")
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/health", headers={"Origin": "http://evil.example"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_is_skipped_when_no_origins_configured() -> None:
    settings = Settings(llm_provider="mock", cors_allowed_origins=[])
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_parse_from_comma_separated_env_string() -> None:
    settings = Settings(
        llm_provider="mock",
        cors_allowed_origins="http://localhost:4000, http://127.0.0.1:4000",
    )

    assert settings.cors_allowed_origins == [
        "http://localhost:4000",
        "http://127.0.0.1:4000",
    ]
