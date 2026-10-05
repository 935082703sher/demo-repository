"""End-to-end resolution lifecycle through /assistant/converse (mock provider).

Walks the registration tree to the imei-register card (which defines a
success_check), then exercises the lifecycle: offer -> failure -> alternative,
offer -> success -> resolved, offer -> phone request -> 1170, offer -> unclear
-> request evidence.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app


def _post(client: TestClient, message: str, session: str) -> dict[str, Any]:
    body = client.post(
        "/assistant/converse", json={"message": message, "session_id": session}
    ).json()
    return dict(body)


def _walk_to_register(client: TestClient, session: str) -> dict[str, Any]:
    _post(client, "telefonim royxatdan otmayapti", session)  # opens the tree
    _post(client, "abroad", session)  # device_origin = imported -> customs
    _post(client, "no", session)  # declaration within norm -> error node
    return _post(client, "payment", session)  # payment/term option -> imei-register


def test_card_with_success_check_is_offered_not_closed() -> None:
    with TestClient(create_app()) as client:
        offer = _walk_to_register(client, "life-offer")
        assert offer["done"] is False
        assert offer["card_id"] == "imei-register"
        assert offer["status"] == "waiting_for_result"
        values = {o["value"] for o in offer["options"]}
        assert "outcome:success" in values and "outcome:failure" in values


def test_failure_offers_the_alternative_card() -> None:
    with TestClient(create_app()) as client:
        _walk_to_register(client, "life-fail")
        nxt = _post(client, "outcome:failure", "life-fail")
        assert nxt["card_id"] == "imei-clone"  # on_failure.next_card
        assert nxt["status"] == "trying_alternative"
        assert nxt["done"] is False


def test_success_resolves_the_case() -> None:
    with TestClient(create_app()) as client:
        _walk_to_register(client, "life-ok")
        done = _post(client, "outcome:success", "life-ok")
        assert done["done"] is True
        assert done["status"] == "resolved"


def test_phone_request_recommends_1170_with_summary() -> None:
    with TestClient(create_app()) as client:
        _walk_to_register(client, "life-1170")
        out = _post(client, "1170 ga qo'ng'iroq qilmoqchiman", "life-1170")
        assert out["done"] is True
        assert out["call_1170"] is True
        assert out["phone"] == "1170"
        assert out["status"] == "call_1170_recommended"
        assert "1170" in out["reply"] and "imei-register" not in out["reply"]  # title, not id


def test_unclear_requests_evidence_and_keeps_the_case() -> None:
    with TestClient(create_app()) as client:
        _walk_to_register(client, "life-unclear")
        out = _post(client, "outcome:unclear", "life-unclear")
        assert out["done"] is False
        assert out["status"] == "waiting_for_result"  # card not discarded
        assert "xato" in out["reply"].lower()  # asks for the error text
