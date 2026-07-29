"""Typed chat workflow tests."""

from fastapi.testclient import TestClient


def test_valid_chat_request_asks_structured_follow_up(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={
            "language": "uz",
            "message": "Mening hududimda mobil internet juda sekin",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "uz"
    assert body["category"] == "network_quality"
    assert body["state"] == "follow_up"
    assert body["fields_missing"][0] == "operator"
    assert body["submission_allowed"] is False
    assert body["grounded"] is False
    assert "AI yordamchisi" in body["reply"]


def test_ai_disclosure_is_only_added_on_first_session_response(client: TestClient) -> None:
    first = client.post(
        "/api/v1/chat",
        json={"language": "en", "message": "Mobile internet is slow"},
    ).json()
    second = client.post(
        "/api/v1/chat",
        json={
            "session_id": first["session_id"],
            "language": "en",
            "message": "Mobile internet remains slow",
        },
    ).json()

    assert "interacting with an AI assistant" in first["reply"]
    assert "interacting with an AI assistant" not in second["reply"]


def test_missing_language_requests_selection(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"message": "Mobile network issue"})

    assert response.status_code == 200
    body = response.json()
    assert body["language"] is None
    assert body["state"] == "language_selection"
    assert "uz, ru, or en" in body["reply"]


def test_invalid_language_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"language": "de", "message": "Network issue"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_empty_message_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/chat", json={"language": "en", "message": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_oversized_message_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"language": "en", "message": "x" * 4001},
    )

    assert response.status_code == 422


def test_malformed_json_has_safe_error(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_unrelated_question_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"language": "en", "message": "What is the weather today?"},
    )

    body = response.json()
    assert body["response_type"] == "refusal"
    assert body["requires_human"] is False
    assert "RTMC services" in body["reply"]


def test_unsupported_factual_question_has_no_answer(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"language": "en", "message": "What is the IMEI registration fee?"},
    )

    body = response.json()
    assert body["grounded"] is False
    assert body["sources"] == []
    assert body["requires_human"] is True
    assert body["handoff_reason"] == "no_approved_source"


def test_explicit_demo_fixture_can_prove_grounding(client: TestClient) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"language": "en", "message": "Show the IMEI demo fixture"},
    )

    body = response.json()
    assert body["state"] == "answer"
    assert body["grounded"] is True
    assert body["sources"][0]["document_id"] == "DEMO-EN-IMEI-001"
    assert body["sources"][0]["demo_only"] is True
    assert "NOT APPROVED FOR PRODUCTION" in body["reply"]


def test_unknown_request_escalates_after_one_clarification(client: TestClient) -> None:
    first = client.post(
        "/api/v1/chat",
        json={"language": "en", "message": "An unusual RTMC matter"},
    )
    session_id = first.json()["session_id"]

    second = client.post(
        "/api/v1/chat",
        json={
            "session_id": session_id,
            "language": "en",
            "message": "It is still unusual and unclear",
        },
    )

    assert first.json()["state"] == "follow_up"
    assert second.json()["state"] == "human_handoff"
    assert second.json()["handoff_reason"] == "unclear_after_clarification"


def test_all_languages_return_matching_follow_up(client: TestClient) -> None:
    cases = [
        ("uz", "Mobil internet juda sekin", "Qaysi mobil operator"),
        ("ru", "Мобильный интернет очень медленный", "какого мобильного оператора"),
        ("en", "Mobile internet is very slow", "Which mobile operator"),
    ]

    for language, message, expected in cases:
        response = client.post(
            "/api/v1/chat",
            json={"language": language, "message": message},
        )
        assert response.status_code == 200
        assert expected in response.json()["reply"]
