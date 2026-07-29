"""Consent, version, idempotency, and non-submission invariants."""

from typing import cast

from fastapi.testclient import TestClient


def _create_complete_draft(client: TestClient, fields: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "en",
            "category": "network_quality",
            "fields": fields,
        },
    )
    assert response.status_code == 200
    return cast(dict[str, object], response.json()["draft"])


def _submit_payload(
    version: int, *, consent: bool = True, key: str = "demo-key-0001"
) -> dict[str, object]:
    return {
        "consent": consent,
        "draft_version": version,
        "privacy_notice_version": "demo-privacy-v1",
        "idempotency_key": key,
    }


def test_submit_without_consent_is_rejected(
    client: TestClient,
    complete_network_fields: dict[str, str],
) -> None:
    draft = _create_complete_draft(client, complete_network_fields)

    response = client.post(
        f"/api/v1/complaints/{draft['draft_id']}/submit",
        json=_submit_payload(1, consent=False),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "explicit_consent_required"


def test_incomplete_draft_is_rejected(client: TestClient) -> None:
    draft = client.post(
        "/api/v1/complaints/draft",
        json={
            "language": "en",
            "category": "network_quality",
            "fields": {"operator": "Demo Operator"},
        },
    ).json()["draft"]

    response = client.post(
        f"/api/v1/complaints/{draft['draft_id']}/submit",
        json=_submit_payload(1),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "incomplete_draft"


def test_stale_submit_version_is_rejected(
    client: TestClient,
    complete_network_fields: dict[str, str],
) -> None:
    draft = _create_complete_draft(client, complete_network_fields)
    updated = client.post(
        "/api/v1/complaints/draft",
        json={
            "session_id": draft["session_id"],
            "draft_id": draft["draft_id"],
            "expected_version": 1,
            "language": "en",
            "category": "network_quality",
            "fields": {"impact": "Updated synthetic impact"},
        },
    ).json()["draft"]

    response = client.post(
        f"/api/v1/complaints/{draft['draft_id']}/submit",
        json=_submit_payload(1),
    )

    assert updated["version"] == 2
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_draft_version"


def test_demo_submit_never_returns_official_case_number(
    client: TestClient,
    complete_network_fields: dict[str, str],
) -> None:
    draft = _create_complete_draft(client, complete_network_fields)

    response = client.post(
        f"/api/v1/complaints/{draft['draft_id']}/submit",
        json=_submit_payload(1),
    )

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["officially_registered"] is False
    assert response.json()["case_number"] is None
    assert response.json()["status"] == "official_integration_not_configured"


def test_duplicate_submit_is_an_idempotent_replay(
    client: TestClient,
    complete_network_fields: dict[str, str],
) -> None:
    draft = _create_complete_draft(client, complete_network_fields)
    url = f"/api/v1/complaints/{draft['draft_id']}/submit"
    payload = _submit_payload(1)

    first = client.post(url, json=payload)
    second = client.post(url, json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    assert first.json()["case_number"] is second.json()["case_number"] is None


def test_second_idempotency_key_is_rejected(
    client: TestClient,
    complete_network_fields: dict[str, str],
) -> None:
    draft = _create_complete_draft(client, complete_network_fields)
    url = f"/api/v1/complaints/{draft['draft_id']}/submit"
    assert client.post(url, json=_submit_payload(1, key="demo-key-0001")).status_code == 200

    second = client.post(url, json=_submit_payload(1, key="demo-key-0002"))

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_submit"


def test_wrong_privacy_notice_version_is_rejected(
    client: TestClient,
    complete_network_fields: dict[str, str],
) -> None:
    draft = _create_complete_draft(client, complete_network_fields)
    payload = _submit_payload(1)
    payload["privacy_notice_version"] = "old-notice"

    response = client.post(
        f"/api/v1/complaints/{draft['draft_id']}/submit",
        json=payload,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "privacy_notice_version_mismatch"
