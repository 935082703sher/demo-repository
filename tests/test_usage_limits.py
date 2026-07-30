"""Server-owned logical LLM quota behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.enums import Language
from app.domain.schemas import LLMRequest, LLMResult
from app.i18n.messages import usage_limit_message
from app.main import create_app
from app.repositories.usage_repository import InMemoryUsageRepository
from app.services.usage_limits import UsageLimitService


class CountingProvider:
    """Count deterministic provider calls without network access."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        return LLMResult(text=request.passages[0], citations=[request.source_ids[0]])


def test_configured_limits_block_next_logical_request() -> None:
    for limit in (5, 10):
        repository = InMemoryUsageRepository()
        service = UsageLimitService(repository, limit=limit, window_seconds=86400)
        session_id = uuid4()

        assert all(service.authorize(session_id).allowed for _ in range(limit))
        assert service.authorize(session_id).allowed is False
        assert service.snapshot(session_id).logical_requests == limit


def test_quota_isolated_between_sessions_and_resets() -> None:
    now = datetime(2026, 7, 30, tzinfo=UTC)

    def clock() -> datetime:
        return now

    repository = InMemoryUsageRepository(clock)
    first = uuid4()
    second = uuid4()
    assert repository.authorize(first, limit=1, window_seconds=60).allowed
    assert not repository.authorize(first, limit=1, window_seconds=60).allowed
    assert repository.authorize(second, limit=1, window_seconds=60).allowed

    now += timedelta(seconds=61)
    assert repository.authorize(first, limit=1, window_seconds=60).allowed


def test_in_memory_restart_loses_usage_state() -> None:
    session_id = uuid4()
    first = InMemoryUsageRepository()
    assert first.authorize(session_id, limit=1, window_seconds=60).allowed
    assert not first.authorize(session_id, limit=1, window_seconds=60).allowed

    restarted = InMemoryUsageRepository()
    assert restarted.authorize(session_id, limit=1, window_seconds=60).allowed


def test_api_blocks_after_quota_and_ignores_browser_counter() -> None:
    provider = CountingProvider()
    settings = Settings(
        llm_generation_limit_per_session=1,
        request_rate_limit_per_minute=20,
    )
    with TestClient(create_app(settings=settings, provider=provider)) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "language": "en",
                "message": "Show the IMEI demo fixture",
                "llm_usage_count": 999999,
            },
        )
        session_id = first.json()["session_id"]
        second = client.post(
            "/api/v1/chat",
            json={
                "session_id": session_id,
                "message": "Show the IMEI demo fixture",
                "llm_usage_count": 0,
            },
        )

    assert first.json()["grounded"] is True
    assert second.json()["response_type"] == "usage_limit_reached"
    assert second.json()["limit"] == 1
    assert second.json()["remaining"] == 0
    assert second.json()["human_handoff_available"] is True
    assert second.json()["officially_registered"] is False
    assert second.json()["case_number"] is None
    assert provider.calls == 1


def test_out_of_scope_and_follow_up_do_not_consume_quota() -> None:
    provider = CountingProvider()
    usage = InMemoryUsageRepository()
    settings = Settings(
        llm_generation_limit_per_session=1,
        request_rate_limit_per_minute=20,
    )
    with TestClient(
        create_app(settings=settings, provider=provider, usage_repository=usage)
    ) as client:
        refused = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Give me a recipe"},
        )
        session_id = UUID(refused.json()["session_id"])
        follow_up = client.post(
            "/api/v1/chat",
            json={"session_id": str(session_id), "message": "My mobile internet is slow"},
        )
        grounded = client.post(
            "/api/v1/chat",
            json={"session_id": str(session_id), "message": "Show the IMEI demo fixture"},
        )

    snapshot = usage.snapshot(session_id, limit=1, window_seconds=86400)
    assert refused.json()["response_type"] == "refusal"
    assert follow_up.json()["response_type"] == "follow_up"
    assert grounded.json()["grounded"] is True
    assert snapshot.logical_requests == 1
    assert snapshot.provider_attempts == 1


def test_usage_limit_contact_variants_never_invent_values() -> None:
    settings = Settings(
        llm_generation_limit_per_session=1,
        request_rate_limit_per_minute=20,
        approved_contact_url="https://example.invalid/approved-contact",
    )
    with TestClient(create_app(settings=settings)) as client:
        first = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Show the IMEI demo fixture"},
        )
        limited = client.post(
            "/api/v1/chat",
            json={
                "session_id": first.json()["session_id"],
                "message": "Show the IMEI demo fixture",
            },
        )

    message = limited.json()["reply"]
    assert "https://example.invalid/approved-contact" in message
    assert "call " not in message.lower()
    assert "phone" not in message.lower()


def test_deterministic_draft_and_submit_continue_after_quota_exhaustion() -> None:
    settings = Settings(
        llm_generation_limit_per_session=1,
        request_rate_limit_per_minute=20,
    )
    complete_fields = {
        "operator": "Synthetic Operator",
        "service_type": "mobile data",
        "region": "Synthetic Region",
        "district": "Synthetic District",
        "approximate_location": "Synthetic location",
        "event_time": "2026-07-30T08:00:00Z",
        "frequency": "daily",
        "duration": "five minutes",
        "impact": "Synthetic service impact",
    }
    with TestClient(create_app(settings=settings)) as client:
        first = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Show the IMEI demo fixture"},
        )
        limited = client.post(
            "/api/v1/chat",
            json={
                "session_id": first.json()["session_id"],
                "message": "Show the IMEI demo fixture",
            },
        )
        draft = client.post(
            "/api/v1/complaints/draft",
            json={
                "session_id": first.json()["session_id"],
                "language": "en",
                "category": "network_quality",
                "fields": complete_fields,
            },
        ).json()["draft"]
        reviewed = client.get(f"/api/v1/complaints/{draft['draft_id']}")
        submitted = client.post(
            f"/api/v1/complaints/{draft['draft_id']}/submit",
            json={
                "consent": True,
                "draft_version": 1,
                "privacy_notice_version": "demo-privacy-v1",
                "idempotency_key": "after-quota-demo",
            },
        )

    assert limited.json()["response_type"] == "usage_limit_reached"
    assert reviewed.status_code == 200
    assert submitted.status_code == 200
    assert submitted.json()["officially_registered"] is False
    assert submitted.json()["case_number"] is None


def test_handoff_and_draft_operations_do_not_consume_llm_quota() -> None:
    usage = InMemoryUsageRepository()
    with TestClient(create_app(usage_repository=usage)) as client:
        initial = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Give me a recipe"},
        )
        session_id = initial.json()["session_id"]
        handoff = client.post(
            "/api/v1/chat",
            json={"session_id": session_id, "message": "I want a human operator"},
        )
        draft = client.post(
            "/api/v1/complaints/draft",
            json={
                "session_id": session_id,
                "language": "en",
                "category": "other",
                "fields": {
                    "description": "Synthetic matter",
                    "desired_outcome": "Human review",
                },
            },
        ).json()["draft"]
        client.get(f"/api/v1/complaints/{draft['draft_id']}")
        client.post(
            f"/api/v1/complaints/{draft['draft_id']}/submit",
            json={
                "consent": True,
                "draft_version": 1,
                "privacy_notice_version": "demo-privacy-v1",
                "idempotency_key": "no-quota-demo",
            },
        )

    snapshot = usage.snapshot(UUID(session_id), limit=10, window_seconds=86400)
    assert handoff.json()["handoff_reason"] == "citizen_requested_human"
    assert snapshot.logical_requests == 0
    assert snapshot.provider_attempts == 0


def test_usage_contact_templates_render_only_configured_values() -> None:
    for language in Language:
        both = usage_limit_message(
            language,
            "+998 00 000 00 00",
            "https://example.invalid/contact",
        )
        url_only = usage_limit_message(language, None, "https://example.invalid/contact")
        neutral = usage_limit_message(language, None, None)

        assert "+998 00 000 00 00" in both
        assert "https://example.invalid/contact" in both
        assert "+998" not in url_only
        assert "{phone}" not in url_only
        assert "http" not in neutral
        assert "+998" not in neutral
