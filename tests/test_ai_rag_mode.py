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


def _recording_app(replies: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
    """An AI+RAG app whose model returns ``replies`` in turn and records each prompt."""
    app = create_app(settings=Settings(ai_rag_only=True))
    prompts: list[dict[str, Any]] = []

    async def complete(prompt: str) -> str:
        prompts.append(json.loads(prompt))
        return json.dumps(replies[min(len(prompts), len(replies)) - 1])

    app.state.ai_rag = AiRagResponder(complete, GroundingValidator(), model_name="test-model")
    return app, prompts


def test_topic_switch_from_mnp_to_imei_retrieves_imei_sources() -> None:
    # Regression: the domain was fixed by the session's first topic, so an IMEI question
    # after an MNP one was answered from MNP sources ("raqamni ko'chirish...").
    answer = {"type": "answer", "reply": "Tushunarli.", "used_sources": []}
    app, prompts = _recording_app([answer])
    with TestClient(app) as client:
        for text in ("MNP nima", "Imei kodni royxatdan otkazmoqchiman tartibi qanday"):
            client.post("/assistant/converse", json={"message": text, "session_id": "sw"})
    second = prompts[1]
    assert second["open_request"].startswith("Imei kodni")
    assert not any(e["id"].startswith("kb-mnp3275:") for e in second["evidence"])


def test_short_answer_to_a_pending_question_keeps_the_open_request() -> None:
    # Regression: after "Siz O'zbekiston fuqarosimisiz?" the reply "ha" lost the request
    # and got a bare "Xo'p, tushunarli."; the model must see both the question it asked
    # and the request it belongs to, and retrieval must search for that request.
    question = {"type": "question", "reply": "Siz O'zbekiston fuqarosimisiz?", "used_sources": []}
    answer = {"type": "answer", "reply": "Tushunarli.", "used_sources": []}
    app, prompts = _recording_app([question, answer, answer])
    with TestClient(app) as client:
        for text in ("Imei kodni royxatdan otkazmoqchiman tartibi qanday", "ha", "online"):
            client.post("/assistant/converse", json={"message": text, "session_id": "pq"})
    after_yes, after_online = prompts[1], prompts[2]
    assert after_yes["pending_question"] == "Siz O'zbekiston fuqarosimisiz?"
    assert after_yes["open_request"].startswith("Imei kodni")
    assert after_online["pending_question"] is None  # answered, no longer pending
    assert after_online["open_request"].startswith("Imei kodni")
    assert after_online["evidence"]  # "online" alone retrieves via the open request


def test_evidence_keeps_every_relevant_answer_of_one_document() -> None:
    # Regression: evidence was de-duplicated by DOCUMENT id, so of five FAQ answers in
    # one file only the first reached the model and the procedure itself was dropped.
    import pytest

    from app.api.routes.case import _ai_rag_evidence
    from app.domain.case_state import CaseState
    from app.services.kb_retriever import get_retriever

    query = "Imei kodni royxatdan otkazmoqchiman tartibi qanday"
    hits = get_retriever().retrieve(query, 5, domain="imei")
    if len({h.chunk.doc_id for h in hits}) == len(hits):
        pytest.skip("needs the built KB index (kb/out), where one document has many hits")
    app = create_app(settings=Settings())
    case = CaseState(case_id="c", session_id="s", domain="imei")
    ev = asyncio.run(_ai_rag_evidence(app.state.legal_reasoning, app.state.tariffs, case, query))
    kb_ids = [e.source_id for e in ev if not e.source_id.startswith("vmq778_clause")]
    assert len(kb_ids) >= 3
