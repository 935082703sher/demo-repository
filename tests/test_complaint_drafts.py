"""Complaint draft creation, editing, review, and cancellation tests."""

from fastapi.testclient import TestClient


def test_create_incomplete_draft(client: TestClient) -> None:
    response = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "en",
            "category": "network_quality",
            "fields": {"operator": "Demo Operator"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["version"] == 1
    assert body["draft"]["complete"] is False
    assert "service_type" in body["draft"]["fields_missing"]
    assert body["consent_required"] is False
    assert body["submission_allowed"] is False
    assert "only a draft" in body["reply"]


def test_draft_version_increments_after_edit(client: TestClient) -> None:
    created = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "en",
            "category": "website_issue",
            "fields": {"page_url": "https://example.invalid/demo"},
        },
    ).json()["draft"]

    updated = client.post(
        "/api/v1/complaints/draft",
        json={
            "session_id": created["session_id"],
            "draft_id": created["draft_id"],
            "expected_version": 1,
            "language": "en",
            "category": "website_issue",
            "fields": {"action_attempted": "Open the synthetic form"},
        },
    )

    assert updated.status_code == 200
    draft = updated.json()["draft"]
    assert draft["version"] == 2
    assert draft["draft_hash"] != created["draft_hash"]
    assert draft["fields"]["page_url"] == "https://example.invalid/demo"


def test_stale_draft_edit_is_rejected(client: TestClient) -> None:
    created = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "en",
            "category": "other",
            "fields": {"description": "Synthetic issue"},
        },
    ).json()["draft"]
    payload = {
        "draft_id": created["draft_id"],
        "expected_version": 1,
        "language": "en",
        "category": "other",
        "fields": {"desired_outcome": "Human review"},
    }
    assert client.post("/api/v1/complaints/draft", json=payload).status_code == 200

    stale = client.post("/api/v1/complaints/draft", json=payload)

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_draft_version"


def test_unsupported_draft_field_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "en",
            "category": "imei",
            "fields": {"full_imei": "000000000000000"},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_draft_fields"
    assert "000000000000000" not in response.text


def test_cancelled_draft_cannot_be_edited(client: TestClient) -> None:
    created = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "en",
            "category": "other",
            "fields": {"description": "Synthetic issue"},
        },
    ).json()["draft"]

    cancelled = client.delete(f"/api/v1/complaints/{created['draft_id']}")
    update = client.post(
        "/api/v1/complaints/draft",
        json={
            "draft_id": created["draft_id"],
            "expected_version": 1,
            "language": "en",
            "category": "other",
            "fields": {"desired_outcome": "Review"},
        },
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["cancelled"] is True
    assert update.status_code == 409
    assert update.json()["error"]["code"] == "draft_cancelled"


def test_cancellation_uses_draft_language(client: TestClient) -> None:
    created = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "ru",
            "category": "other",
            "fields": {"description": "Синтетическая проблема"},
        },
    ).json()["draft"]

    response = client.delete(f"/api/v1/complaints/{created['draft_id']}")

    assert "отменён" in response.json()["message"]


def test_unknown_draft_is_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/complaints/00000000-0000-0000-0000-000000000001")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "draft_not_found"
