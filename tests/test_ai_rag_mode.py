"""AI + RAG only mode: grounded natural answers, open failures, no canned fallback."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.ai_rag import AiRagResponder, AiRagResult, Evidence
from app.services.grounding import GroundingValidator

_EVIDENCE = [
    Evidence(source_id="KB-1", title="Tarif", text="Ro'yxatdan o'tkazish narxi 82 400 so'm."),
    Evidence(source_id="VMQ-778:6", title="VMQ-778 6", text="To'lov har bir IMEI uchun alohida."),
]


def _responder(obj: dict[str, Any] | None) -> AiRagResponder:
    if obj is None:
        return AiRagResponder(None, GroundingValidator())  # no model wired

    async def complete(_prompt: str) -> str:
        return json.dumps(obj)

    return AiRagResponder(complete, GroundingValidator(), model_name="test-model")


def _run(obj: dict[str, Any] | None, *, message: str = "narxi qancha") -> AiRagResult:
    from app.domain.case_state import CaseState

    case = CaseState(case_id="c", session_id="s")
    return asyncio.run(_responder(obj).respond(case, message, "uz", _EVIDENCE))


def test_no_model_reports_an_open_technical_error_not_a_canned_answer() -> None:
    res = _run(None)
    assert res.error is True
    assert "Texnik xatolik" in res.reply


def test_grounded_answer_passes_and_returns_its_sources() -> None:
    res = _run({"type": "answer", "reply": "Narxi 82 400 so'm.", "used_sources": ["KB-1"]})
    assert res.error is False and res.is_question is False
    assert res.sources == [("KB-1", "Tarif")]


def test_an_invented_number_is_rejected_as_ungrounded() -> None:
    res = _run({"type": "answer", "reply": "Narxi 99 999 so'm.", "used_sources": ["KB-1"]})
    assert res.error is False
    assert "taxmin qilmayman" in res.reply  # honest limitation, not the invented figure
    assert "99 999" not in res.reply


def test_a_fabricated_citation_is_rejected() -> None:
    res = _run({"type": "answer", "reply": "Shunday.", "used_sources": ["KB-DOES-NOT-EXIST"]})
    assert "taxmin qilmayman" in res.reply


def test_a_live_lookup_claim_is_not_shipped() -> None:
    res = _run({"type": "answer", "reply": "Arizangizni tekshirdim.", "used_sources": ["KB-1"]})
    assert res.error is True


def test_a_clarifying_question_needs_no_source() -> None:
    res = _run({"type": "question", "reply": "Telefon qayerdan?", "used_sources": []})
    assert res.is_question is True and res.error is False and res.sources == []


def test_a_greeting_without_numbers_or_sources_is_allowed() -> None:
    res = _run(
        {"type": "answer", "reply": "Assalomu alaykum! Qanday yordam beray?", "used_sources": []},
        message="salom",
    )
    assert res.error is False and res.sources == []


def test_payment_question_evidence_carries_the_fee_clauses_and_computed_tariff() -> None:
    # A legal-basis-for-the-fee question must always get the fee clauses (42 + Annex 6)
    # and the computed amounts, regardless of how retrieval ranked the clauses.
    from app.api.routes.case import _ai_rag_evidence
    from app.domain.case_state import CaseState

    app = create_app(settings=Settings())
    engine = app.state.legal_reasoning
    tariffs = app.state.tariffs
    case = CaseState(case_id="c", session_id="s", domain="imei")
    ev = asyncio.run(
        _ai_rag_evidence(engine, tariffs, case, "qonuniy dalil bormi qancha to'lashim haqida")
    )
    ids = " ".join(e.source_id for e in ev)
    text = " ".join(e.text for e in ev)
    assert "42" in ids  # clause 42: fee amounts are set in Annex 6
    assert "ilova" in ids  # the Annex 6 amounts table / computed tariff
    assert "82400" in text and "103000" in text  # the exact computed amounts are present


def test_mode_on_with_no_model_fails_openly_and_shows_no_menu() -> None:
    # The mock provider wires no AI+RAG model, so every turn must fail openly - never a
    # tree, a menu, or a canned domain answer.
    app = create_app(settings=Settings(ai_rag_only=True))
    with TestClient(app) as client:
        payload = {"message": "imeini royxatdan otkazish uchun qancha tolov", "session_id": "r1"}
        body = dict(client.post("/assistant/converse", json=payload).json())
    assert "Texnik xatolik" in body["reply"]
    assert body["requires_human"] is True
    assert body["options"] == []  # no menu / buttons in this mode
