"""Internal Stage 3C facade contracts; none are public API models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ComplaintWorkflowState,
    HandoffReason,
    HumanHandoff,
    HumanReviewStatus,
    MessageKey,
    SecureFieldType,
    SecureValueReference,
)
from app.domain.enums import Category, Language
from app.domain.schemas import ShortText, StrictModel


class OrchestrationOutcome(StrEnum):
    """Closed local outcomes with no official-processing state."""

    LANGUAGE_SELECTION = "language_selection"
    SCOPE_REFUSAL = "scope_refusal"
    CLARIFICATION = "clarification"
    COLLECTING = "collecting"
    REVIEW_READY = "review_ready"
    HUMAN_HANDOFF = "human_handoff"
    CANCELLED = "cancelled"
    SUBMISSION_BLOCKED = "submission_blocked"


class GovernedComplaintInput(StrictModel):
    """Synthetic/internal structured input, deliberately separate from public schemas."""

    session_id: UUID | None = None
    draft_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)
    language: Language | None = None
    message: str = Field(min_length=1, max_length=4000)
    applicant_type: ApplicantType = ApplicantType.UNKNOWN
    appeal_kind: AppealKind = AppealKind.UNKNOWN
    category: Category | None = None
    subcategory: ComplaintSubcategory = ComplaintSubcategory.UNKNOWN
    fields: dict[str, ShortText]
    required_secure_fields: list[SecureFieldType] = Field(default_factory=list)
    secure_references: list[SecureValueReference] = Field(default_factory=list)
    human_review_reasons: list[HandoffReason] = Field(default_factory=list)


class MaskedSecureReference(StrictModel):
    """Citizen-safe secure-field indicator without the opaque internal identifier."""

    field_type: SecureFieldType
    masked_display: Literal["***"] = "***"


class GovernedComplaintReview(StrictModel):
    """Complete non-sensitive local review before consent."""

    applicant_type: ApplicantType
    appeal_kind: AppealKind
    category: Category
    subcategory: ComplaintSubcategory
    subject: str
    structured_issue_description: str
    occurrence_details: dict[str, str]
    secure_reference_indicators: list[MaskedSecureReference]
    missing_fields: list[str]
    human_review_status: HumanReviewStatus
    draft_id: UUID
    synthetic_session_id: UUID
    version: int
    canonical_hash: str
    language: Language
    privacy_notice_version: str
    consent_wording_version: str
    not_officially_registered_notice: str
    officially_registered: Literal[False] = False
    case_number: None = None
    official_status: None = None


class GovernedHandoffResult(StrictModel):
    """Typed handoff that cannot imply delivery to an operator or authority."""

    handoff: HumanHandoff
    preserved_reason: HandoffReason
    officially_registered: Literal[False] = False
    case_number: None = None
    official_status: None = None


class GovernedOrchestrationResult(StrictModel):
    """One deterministic local orchestration result."""

    outcome: OrchestrationOutcome
    session_id: UUID
    language: Language | None
    workflow_state: ComplaintWorkflowState | None = None
    message_key: MessageKey | None = None
    follow_up_key: str | None = None
    follow_up_question: str | None = None
    review: GovernedComplaintReview | None = None
    handoff: GovernedHandoffResult | None = None
    created_at: datetime
    officially_registered: Literal[False] = False
    case_number: None = None
    official_status: None = None
