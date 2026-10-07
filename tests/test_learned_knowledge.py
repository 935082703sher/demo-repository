"""Expert learning loop (Phase 8-9): gap -> expert answer -> draft -> approve ->
published versioned article -> a later similar question is answered from it.

This is the spec's TEST 5 end-to-end, plus reject, validation and versioning/rollback.
Everything runs on the mock provider (deterministic template draft composer).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.knowledge_article import KnowledgeContent, KnowledgeDraft
from app.main import create_app
from app.services.learned_knowledge import InMemoryLearnedKnowledgeStore, ValidationError

_ADMIN = ("admin", "secret")


def _app() -> Any:
    return create_app(
        settings=Settings(_env_file=None, environment="test", admin_password="secret")
    )


# --- store unit: validation, versioning, rollback ---


def _content(
    title: str = "IMEI klon", solution: str = "1170 ga murojaat qiling"
) -> KnowledgeContent:
    return KnowledgeContent(
        title=title, domain="imei", solution=solution, keywords=["klon", "imei"]
    )


def test_approve_requires_expert_and_fields() -> None:
    store = InMemoryLearnedKnowledgeStore()
    asyncio.run(store.add_draft(KnowledgeDraft(draft_id="d1", content=_content())))
    try:
        asyncio.run(store.approve("d1", expert=""))  # no expert
        raise AssertionError("expected ValidationError")
    except ValidationError as exc:
        assert "expert" in str(exc)
    # missing solution -> invalid
    asyncio.run(store.add_draft(KnowledgeDraft(draft_id="d2", content=_content(solution=""))))
    try:
        asyncio.run(store.approve("d2", expert="dr"))
        raise AssertionError("expected ValidationError")
    except ValidationError as exc:
        assert "missing_required_fields" in str(exc)


def test_duplicate_is_rejected() -> None:
    store = InMemoryLearnedKnowledgeStore()
    asyncio.run(store.add_draft(KnowledgeDraft(draft_id="d1", content=_content())))
    asyncio.run(store.approve("d1", expert="dr"))
    asyncio.run(
        store.add_draft(KnowledgeDraft(draft_id="d2", content=_content()))
    )  # same title+domain
    try:
        asyncio.run(store.approve("d2", expert="dr"))
        raise AssertionError("expected ValidationError")
    except ValidationError as exc:
        assert "duplicate" in str(exc)


def test_publish_search_and_rollback() -> None:
    store = InMemoryLearnedKnowledgeStore()
    asyncio.run(store.add_draft(KnowledgeDraft(draft_id="d1", content=_content())))
    article = asyncio.run(store.approve("d1", expert="dr", change_reason="first"))
    assert article.version == 1 and article.approved_by == "dr"
    hit = asyncio.run(store.search("imei klon bo'lsa nima qilay"))
    assert hit is not None and hit.article.article_id == article.article_id
    # rollback to a known version keeps history usable
    assert asyncio.run(store.rollback(article.article_id, 1)) is not None


# --- full workflow through the admin API + converse (spec TEST 5) ---


def _post(client: TestClient, message: str, session: str) -> dict[str, Any]:
    return dict(
        client.post("/assistant/converse", json={"message": message, "session_id": session}).json()
    )


def test_expert_learning_loop_end_to_end() -> None:
    app = _app()
    # Seed a gap directly (as an abstention would), then run the expert workflow.
    gap = asyncio.run(
        app.state.knowledge_gaps.record(
            question="Rouming paytida IMEI ro'yxatga olinadimi",
            domain="imei",
            intent=None,
            reason="no_evidence",
        )
    )
    with TestClient(app) as client:
        # Expert answers the gap -> a draft is created (not yet answerable).
        r = client.post(
            f"/admin/knowledge-gaps/{gap.gap_id}/answer",
            json={
                "expert": "dr. Aliyev",
                "expert_answer": (
                    "Rouming qurilmasi mahalliy tarmoqda tarmoq hodisasi bo'lmaguncha "
                    "ro'yxatga olinmaydi; birinchi ulanishdan keyin 30 kun ichida olinadi."
                ),
            },
            auth=_ADMIN,
        )
        assert r.status_code == 200
        draft_id = r.json()["draft"]["draft_id"]
        # It is pending, not answerable yet.
        assert any(
            d["draft_id"] == draft_id
            for d in client.get("/admin/knowledge-drafts", auth=_ADMIN).json()["drafts"]
        )

        # Approve -> a versioned article is published and the index refreshes.
        approve = client.post(
            f"/admin/knowledge-drafts/{draft_id}/approve",
            json={"expert": "dr. Aliyev", "change_reason": "expert supplied"},
            auth=_ADMIN,
        )
        assert approve.status_code == 200
        article_id = approve.json()["article"]["article_id"]

        # A later, semantically similar question is now answered FROM the learned article.
        body = _post(client, "rouming vaqtida imei ro'yxatga olinadimi", "learn-1")
        sources = [s["doc_id"] for s in (body.get("sources") or [])]
        assert article_id in sources  # answered from the expert-approved article
        assert "30 kun" in body["reply"]  # the expert's solution reached the user

    # The gap is now marked published.
    published = asyncio.run(app.state.knowledge_gaps.list())
    assert any(g.status.value == "published" for g in published)


def test_reject_draft_marks_gap_rejected() -> None:
    app = _app()
    gap = asyncio.run(
        app.state.knowledge_gaps.record(
            question="Test savol", domain="imei", intent=None, reason="no_evidence"
        )
    )
    with TestClient(app) as client:
        r = client.post(
            f"/admin/knowledge-gaps/{gap.gap_id}/answer",
            json={"expert": "dr", "expert_answer": "javob"},
            auth=_ADMIN,
        )
        draft_id = r.json()["draft"]["draft_id"]
        rej = client.post(f"/admin/knowledge-drafts/{draft_id}/reject", auth=_ADMIN)
        assert rej.status_code == 200
    gaps = asyncio.run(app.state.knowledge_gaps.list())
    assert any(g.status.value == "rejected" for g in gaps)
