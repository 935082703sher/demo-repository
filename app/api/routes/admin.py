"""Admin KPI dashboard, protected by HTTP Basic auth.

Access requires ADMIN_PASSWORD to be configured; without it the admin routes are
refused (503) so the dashboard is never accidentally public. Credentials are
compared in constant time.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.core.config import Settings
from app.domain.knowledge_gap import GapStatus, KnowledgeGap
from app.services.audit_log import AuditLog
from app.services.kb_draft import KbDraftComposer
from app.services.knowledge_gap import KnowledgeGapStore
from app.services.learned_knowledge import LearnedKnowledgeStore, ValidationError

router = APIRouter(tags=["admin"])

_security = HTTPBasic()
_ADMIN_PAGE = Path(__file__).parent.parent.parent / "static" / "admin.html"

Credentials = Annotated[HTTPBasicCredentials, Depends(_security)]


def require_admin(request: Request, credentials: Credentials) -> None:
    """Allow only the configured admin; refuse entirely when unconfigured."""
    settings = cast(Settings, request.app.state.settings)
    secret = settings.admin_password
    if secret is None or not secret.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin_not_configured",
        )
    user_ok = secrets.compare_digest(credentials.username, settings.admin_user)
    password_ok = secrets.compare_digest(credentials.password, secret.get_secret_value())
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


AdminGuard = Annotated[None, Depends(require_admin)]


@router.get("/admin", include_in_schema=False)
def admin_page(_: AdminGuard) -> FileResponse:
    """Serve the KPI dashboard (Basic-auth protected)."""
    return FileResponse(_ADMIN_PAGE)


@router.get("/admin/metrics")
async def admin_metrics(request: Request, _: AdminGuard) -> dict[str, object]:
    """Return the pilot KPIs for the dashboard (Basic-auth protected)."""
    audit = cast(AuditLog, request.app.state.audit_log)
    return await audit.metrics()


@router.get("/admin/knowledge-gaps")
async def admin_knowledge_gaps(
    request: Request, _: AdminGuard, status_filter: str | None = None
) -> dict[str, object]:
    """The expert console: distinct missing-knowledge topics, most frequent first.

    Each item is a grouped gap (the normalised question, how often it was hit, the
    example phrasings, what was searched and why it failed) so an expert can supply
    the missing knowledge once for all the users who asked a variation of it. Admin
    Basic-auth protected; stored questions are already PII-redacted.
    """
    gaps_store = cast(
        "KnowledgeGapStore | None", getattr(request.app.state, "knowledge_gaps", None)
    )
    if gaps_store is None:
        return {"count": 0, "gaps": []}
    valid = {s.value for s in GapStatus}
    status = GapStatus(status_filter) if status_filter in valid else None
    gaps: list[KnowledgeGap] = await gaps_store.list(status=status)
    return {"count": len(gaps), "gaps": [g.model_dump() for g in gaps]}


@router.get("/admin/metrics/trends")
async def admin_metrics_trends(request: Request, _: AdminGuard) -> dict[str, object]:
    """Windowed KPI trends (7/30/90 days) plus a daily series, to show whether the
    assistant is improving over time. Admin Basic-auth protected."""
    audit = cast(AuditLog, request.app.state.audit_log)
    trends = await audit.trends()
    gaps_store = cast(
        "KnowledgeGapStore | None", getattr(request.app.state, "knowledge_gaps", None)
    )
    open_gaps = 0
    if gaps_store is not None:
        open_gaps = sum(1 for g in await gaps_store.list() if g.priority_score() > 0)
    trends["open_knowledge_gaps"] = open_gaps
    return trends


@router.get("/admin/improvement-queue")
async def admin_improvement_queue(request: Request, _: AdminGuard) -> dict[str, object]:
    """Assistant Improvement Queue: unresolved knowledge-gap clusters ranked by impact.

    Each item is a cluster (semantically grouped) with how many users it affects, why
    the assistant failed, and a one-line summary - so an expert can pick the
    highest-impact missing knowledge to teach first via the answer endpoint.
    """
    gaps_store = cast(
        "KnowledgeGapStore | None", getattr(request.app.state, "knowledge_gaps", None)
    )
    if gaps_store is None:
        return {"count": 0, "items": []}
    gaps = await gaps_store.list()
    ranked = sorted(
        (g for g in gaps if g.priority_score() > 0),
        key=lambda g: g.priority_score(),
        reverse=True,
    )
    items = [
        {
            "gap_id": g.gap_id,
            "priority_score": g.priority_score(),
            "affected_users": max(g.frequency, len(g.case_ids)),
            "domain": g.domain,
            "status": g.status.value,
            "reason": g.reason_for_failure,
            "summary": (
                f"{max(g.frequency, len(g.case_ids))} ta foydalanuvchi shunga o'xshash "
                f"savol berdi; ishonchli KB maqolasi yo'q ({g.reason_for_failure}). "
                f"Namuna: {g.question[:120]}"
            ),
            "example_questions": g.example_questions[:5],
        }
        for g in ranked
    ]
    return {"count": len(items), "items": items}


class ExpertAnswer(BaseModel):
    expert: str
    expert_answer: str


class ApproveRequest(BaseModel):
    expert: str
    change_reason: str = ""


@router.post("/admin/knowledge-gaps/{gap_id}/answer")
async def admin_answer_gap(
    gap_id: str, payload: ExpertAnswer, request: Request, _: AdminGuard
) -> dict[str, object]:
    """Expert answers a gap; the AI composes a structured draft for the expert to review.

    The draft is a proposal only - it is NOT answerable until approved. Returns the
    draft so the expert can edit/approve/reject it.
    """
    gaps_store = cast(KnowledgeGapStore, request.app.state.knowledge_gaps)
    composer = cast(KbDraftComposer, request.app.state.kb_draft)
    learned = cast(LearnedKnowledgeStore, request.app.state.learned_knowledge)
    gap = await gaps_store.get(gap_id)
    if gap is None:
        raise HTTPException(status_code=404, detail="gap_not_found")
    content = await composer.compose(gap, payload.expert_answer)
    from app.domain.knowledge_article import KnowledgeDraft

    draft = KnowledgeDraft(
        draft_id=f"draft-{gap_id}",
        gap_id=gap_id,
        content=content,
        source_expert=payload.expert,
        expert_answer=payload.expert_answer,
    )
    await learned.add_draft(draft)
    await gaps_store.set_status(gap_id, GapStatus.DRAFT_CREATED)
    return {"draft": draft.model_dump()}


@router.get("/admin/knowledge-drafts")
async def admin_list_drafts(request: Request, _: AdminGuard) -> dict[str, object]:
    """Pending KB drafts awaiting expert approval."""
    learned = cast(LearnedKnowledgeStore, request.app.state.learned_knowledge)
    drafts = await learned.list_drafts()
    return {"count": len(drafts), "drafts": [d.model_dump() for d in drafts]}


@router.post("/admin/knowledge-drafts/{draft_id}/approve")
async def admin_approve_draft(
    draft_id: str, payload: ApproveRequest, request: Request, _: AdminGuard
) -> dict[str, object]:
    """Approve a draft: validate, publish a versioned article, refresh the index.

    On success the article becomes answerable and the originating gap is marked
    published. Validation (required fields, expert present, no duplicate) is enforced
    here - an AI draft is never published on confidence alone.
    """
    learned = cast(LearnedKnowledgeStore, request.app.state.learned_knowledge)
    gaps_store = cast(KnowledgeGapStore, request.app.state.knowledge_gaps)
    draft = await learned.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    try:
        article = await learned.approve(
            draft_id, expert=payload.expert, change_reason=payload.change_reason
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if draft.gap_id:
        await gaps_store.set_status(draft.gap_id, GapStatus.PUBLISHED)
    return {"article": article.model_dump()}


@router.post("/admin/knowledge-drafts/{draft_id}/reject")
async def admin_reject_draft(draft_id: str, request: Request, _: AdminGuard) -> dict[str, object]:
    """Reject a draft; the originating gap is marked rejected."""
    learned = cast(LearnedKnowledgeStore, request.app.state.learned_knowledge)
    gaps_store = cast(KnowledgeGapStore, request.app.state.knowledge_gaps)
    draft = await learned.reject(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    if draft.gap_id:
        await gaps_store.set_status(draft.gap_id, GapStatus.REJECTED)
    return {"draft": draft.model_dump()}
