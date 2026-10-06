"""The converse flow answers legal questions from matched VMQ-778 rules.

A standalone legal question is answered from the authoritative rules (clause-cited),
not mis-routed to a KB FAQ or dead-ended at 1170; an off-topic question is NOT
captured by the policy lane.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app


def _post(client: TestClient, message: str, session: str, lang: str = "uz") -> dict[str, Any]:
    return dict(
        client.post(
            "/assistant/converse",
            json={"message": message, "session_id": session, "language": lang},
        ).json()
    )


def _vmq_sources(body: dict[str, Any]) -> list[str]:
    return [s["doc_id"] for s in (body.get("sources") or []) if "VMQ-778" in s.get("doc_id", "")]


def test_nonresident_question_answered_from_policy_with_clauses() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "Men xorijiy fuqaroman, telefonim necha kun ishlaydi?", "pol-nr")
        assert body["status"] == "resolved"
        assert _vmq_sources(body)  # cites VMQ-778 clauses
        assert "60 kalendar kun" in body["reply"]  # the non-resident window
        assert body["call_1170"] is False


def test_russian_nonresident_question_answered_from_policy() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "Я нерезидент, сколько дней работает телефон?", "pol-ru", lang="ru")
        assert _vmq_sources(body)
        assert "60" in body["reply"]


def test_importer_question_cites_im40_clause() -> None:
    with TestClient(create_app()) as client:
        body = _post(
            client,
            "Biz import qiluvchimiz, IM-40 rejimida partiya olib keldik, qancha to'lanadi?",
            "pol-imp",
        )
        clauses = _vmq_sources(body)
        assert any("11-band" in c for c in clauses)  # the importer IM-40 clause


def test_offtopic_question_is_not_captured_by_policy() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "Bugun ob-havo qanday?", "pol-off")
        assert _vmq_sources(body) == []  # the law lane did not fire


def test_bare_pricing_question_is_not_hijacked_by_resident_default() -> None:
    # A pricing question with no situation signal falls to the KB, not the policy lane
    # (the resident default alone must never trigger a legal answer).
    with TestClient(create_app()) as client:
        body = _post(client, "Narxi qancha?", "pol-price")
        assert _vmq_sources(body) == []
