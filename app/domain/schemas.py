"""Pydantic API and internal boundary models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain.enums import (
    Category,
    ConversationState,
    DraftStatus,
    EscalationReason,
    KnowledgeStatus,
    Language,
    ResponseType,
    SafetyFlag,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class StrictModel(BaseModel):
    """Base model that rejects undeclared input fields."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    """Minimal health information safe for unauthenticated monitoring."""

    status: str
    service: str
    version: str


class SourceReference(StrictModel):
    """Public citation for an approved or explicitly synthetic demo record."""

    document_id: str
    title: str
    url: str | None
    version: str
    demo_only: bool


class ComplaintDraftReview(StrictModel):
    """Complete draft representation shown to the citizen before consent."""

    draft_id: UUID
    session_id: UUID
    version: int
    draft_hash: str
    status: DraftStatus
    language: Language
    category: Category
    subject: str
    description: str
    fields: dict[str, str]
    fields_missing: list[str]
    personal_data_to_submit: list[str]
    complete: bool
    not_submitted_notice: str
    created_at: datetime
    updated_at: datetime


class ChatRequest(StrictModel):
    """Citizen message sent by the website backend."""

    session_id: UUID | None = None
    language: Language | None = None
    message: NonEmptyText = Field(max_length=4000)


class ChatResponse(StrictModel):
    """Stable response contract for the Nuxt website developer."""

    request_id: UUID
    session_id: UUID
    language: Language | None
    state: ConversationState
    response_type: ResponseType
    category: Category | None
    reply: str
    grounded: bool
    sources: list[SourceReference] = Field(default_factory=list)
    fields_collected: dict[str, str] = Field(default_factory=dict)
    fields_missing: list[str] = Field(default_factory=list)
    draft: ComplaintDraftReview | None = None
    consent_required: bool = False
    submission_allowed: bool = False
    requires_human: bool = False
    handoff_reason: EscalationReason | None = None
    safety_flags: list[SafetyFlag] = Field(default_factory=list)


class DraftUpsertRequest(StrictModel):
    """Create or version an in-memory complaint draft."""

    session_id: UUID | None = None
    draft_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)
    language: Language
    category: Category
    fields: dict[str, ShortText]

    @field_validator("fields")
    @classmethod
    def require_at_least_one_field(cls, value: dict[str, str]) -> dict[str, str]:
        """Avoid meaningless empty draft records."""
        if not value:
            raise ValueError("at least one complaint field is required")
        return value


class DraftResponse(StrictModel):
    """Draft endpoint response."""

    request_id: UUID
    state: ConversationState
    response_type: ResponseType
    reply: str
    consent_required: bool
    submission_allowed: bool
    draft: ComplaintDraftReview


class DraftCancelResponse(StrictModel):
    """Cancellation acknowledgement for an in-memory draft."""

    request_id: UUID
    draft_id: UUID
    state: ConversationState
    cancelled: bool
    message: str


class SubmitRequest(StrictModel):
    """Explicit submit event, bound to an exact draft and notice version."""

    consent: bool
    draft_version: int = Field(ge=1)
    privacy_notice_version: NonEmptyText
    idempotency_key: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
        ),
    ]


class SubmitResponse(StrictModel):
    """Safe Demo 1 result; it can never represent official registration."""

    request_id: UUID
    success: bool
    status: str
    officially_registered: bool
    case_number: None = None
    message: str
    idempotent_replay: bool


class ErrorBody(StrictModel):
    """Safe client-facing API error."""

    code: str
    message: str
    request_id: UUID
    details: list[dict[str, Any]] | None = None


class ErrorResponse(StrictModel):
    """Error envelope shared by validation and domain failures."""

    error: ErrorBody


class KnowledgeRecord(StrictModel):
    """Versioned local knowledge record used by deterministic retrieval."""

    document_id: str
    title: str
    language: Language
    category: Category
    content: str
    keywords: list[str]
    source_url: str | None
    version: str
    status: KnowledgeStatus
    approved_at: datetime | None
    expires_at: datetime | None


class ClassificationResult(StrictModel):
    """Deterministic classifier result; confidence is a rule score, not ML calibration."""

    category: Category
    confidence: float = Field(ge=0, le=1)
    requires_clarification: bool
    requires_human: bool


class LLMRequest(StrictModel):
    """Minimum provider input for a grounded answer."""

    language: Language
    question: str
    category: Category
    passages: list[str]


class LLMResult(StrictModel):
    """Provider output before deterministic validation."""

    text: str


class ConsentRecord(StrictModel):
    """In-memory evidence of an explicit Demo 1 submit event."""

    draft_id: UUID
    draft_version: int
    draft_hash: str
    privacy_notice_version: str
    idempotency_key: str
    request_id: UUID
    recorded_at: datetime
