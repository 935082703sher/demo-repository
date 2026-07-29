"""In-memory complaint draft and safe submit endpoints."""

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request

from app.domain.enums import ConversationState, ResponseType
from app.domain.schemas import (
    ComplaintDraftReview,
    DraftCancelResponse,
    DraftResponse,
    DraftUpsertRequest,
    SubmitRequest,
    SubmitResponse,
)
from app.services.complaint_drafts import ComplaintDraftService, cancelled_message

router = APIRouter(prefix="/api/v1/complaints", tags=["complaints"])


@router.post("/draft", response_model=DraftResponse)
async def upsert_draft(payload: DraftUpsertRequest, request: Request) -> DraftResponse:
    """Create or update a versioned in-memory complaint draft."""
    service = cast(ComplaintDraftService, request.app.state.drafts)
    draft = service.upsert(payload)
    return DraftResponse(
        request_id=request.state.request_id,
        state=ConversationState.DRAFT_REVIEW,
        response_type=ResponseType.DRAFT,
        reply=draft.not_submitted_notice,
        consent_required=draft.complete,
        submission_allowed=False,
        draft=draft,
    )


@router.get("/{draft_id}", response_model=ComplaintDraftReview)
async def get_draft(draft_id: UUID, request: Request) -> ComplaintDraftReview:
    """Return the current in-memory draft for review."""
    service = cast(ComplaintDraftService, request.app.state.drafts)
    return service.get(draft_id)


@router.delete("/{draft_id}", response_model=DraftCancelResponse)
async def cancel_draft(draft_id: UUID, request: Request) -> DraftCancelResponse:
    """Cancel an unsubmitted in-memory draft."""
    service = cast(ComplaintDraftService, request.app.state.drafts)
    draft = service.cancel(draft_id)
    return DraftCancelResponse(
        request_id=request.state.request_id,
        draft_id=draft.draft_id,
        state=ConversationState.CANCELLED,
        cancelled=True,
        message=cancelled_message(draft.language),
    )


@router.post("/{draft_id}/submit", response_model=SubmitResponse)
async def submit_draft(
    draft_id: UUID,
    payload: SubmitRequest,
    request: Request,
) -> SubmitResponse:
    """Record explicit consent but never contact an official RTMC system."""
    service = cast(ComplaintDraftService, request.app.state.drafts)
    return service.submit(draft_id, payload, request.state.request_id)
