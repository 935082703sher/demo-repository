"""Knowledge gaps: abstention records a structured gap, and similar ones group.

The assistant must not invent an answer when the knowledge base cannot support one;
instead it records a gap with context for an expert, and similar questions merge into
one topic with a frequency - the foundation of the human-in-the-loop learning loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from app.domain.knowledge_gap import GapStatus
from app.main import create_app
from app.services.knowledge_gap import InMemoryKnowledgeGapStore


def _record(store: InMemoryKnowledgeGapStore, question: str, **kw: Any) -> Any:
    return asyncio.run(
        store.record(question=question, domain="imei", intent=None, reason="no_evidence", **kw)
    )


def test_distinct_questions_create_distinct_gaps() -> None:
    store = InMemoryKnowledgeGapStore()
    _record(store, "IMEI klonlanganda nima bo'ladi")
    _record(store, "MNP arizasi qancha vaqtda ko'riladi")
    gaps = asyncio.run(store.list())
    assert len(gaps) == 2


def test_similar_questions_group_and_count() -> None:
    store = InMemoryKnowledgeGapStore()
    _record(store, "Internetim ishlamayapti nima qilay", case_id="c1")
    _record(store, "internet ishlamayapti nima qilay men", case_id="c2")
    gaps = asyncio.run(store.list())
    assert len(gaps) == 1  # merged into one topic
    assert gaps[0].frequency == 2
    assert gaps[0].status is GapStatus.GROUPED  # promoted once hit by 2+ users
    assert set(gaps[0].case_ids) == {"c1", "c2"}
    assert len(gaps[0].example_questions) == 2


def test_status_filter_and_transition() -> None:
    store = InMemoryKnowledgeGapStore()
    gap = _record(store, "norezident uchun maxsus tartif bormi")
    asyncio.run(store.set_status(gap.gap_id, GapStatus.NEEDS_EXPERT))
    assert len(asyncio.run(store.list(status=GapStatus.NEEDS_EXPERT))) == 1
    assert asyncio.run(store.list(status=GapStatus.PUBLISHED)) == []


# --- integration: a KB-gap turn records a structured gap (no hallucination) ---


def _post(client: TestClient, message: str, session: str) -> dict[str, Any]:
    return dict(
        client.post("/assistant/converse", json={"message": message, "session_id": session}).json()
    )


def test_rag_abstention_records_a_gap_and_does_not_invent() -> None:
    # The KB answer lane: when there is no evidence it must abstain (no sources) AND
    # record a structured gap for an expert - the core no-hallucination behaviour.
    from app.api.routes.case import _rag_answer
    from app.domain.case_state import CaseState

    app = create_app()
    store = InMemoryKnowledgeGapStore()
    case = CaseState(case_id="kg-c", session_id="kg-s", domain="imei")
    reply = asyncio.run(
        _rag_answer(
            app.state.provider,
            app.state.grounding,
            None,
            case,
            "Menga osh pishirish retseptini aytib bering",
            "uz",
            store,
        )
    )
    assert reply.requires_human is True  # abstained
    assert reply.sources in (None, [])  # nothing invented/cited
    gaps = asyncio.run(store.list())
    assert gaps and gaps[0].reason_for_failure in {"no_evidence", "weak_evidence", "ungroundable"}
    assert gaps[0].question and gaps[0].case_ids == ["kg-c"]
