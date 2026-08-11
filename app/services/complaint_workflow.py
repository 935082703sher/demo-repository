"""Deterministic Stage 3A workflow rules with no official submission capability."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ComplaintWorkflowDraft,
    ComplaintWorkflowState,
    ConsentBinding,
    ConsentState,
    HandoffReason,
    HumanReviewStatus,
    RequirementsProfile,
    SecureValueReference,
    canonical_draft_hash,
)
from app.domain.enums import Category, Language


class WorkflowErrorCode(StrEnum):
    """Stable non-sensitive failures for internal Stage 3A orchestration."""

    INVALID_TRANSITION = "invalid_workflow_transition"
    INCOMPLETE_DRAFT = "workflow_draft_incomplete"
    CLARIFICATION_REQUIRED = "workflow_clarification_required"
    HUMAN_REVIEW_REQUIRED = "workflow_human_review_required"
    PROFILE_MISMATCH = "requirements_profile_mismatch"
    STALE_CONSENT_VERSION = "stale_consent_version"
    STALE_CONSENT_HASH = "stale_consent_hash"
    CONSENT_LANGUAGE_MISMATCH = "consent_language_mismatch"
    PRIVACY_NOTICE_MISMATCH = "privacy_notice_version_mismatch"
    CONSENT_REQUIRED = "current_draft_consent_required"
    CONSENT_TIMESTAMP_INVALID = "consent_timestamp_invalid"
    DRAFT_CANCELLED = "workflow_draft_cancelled"
    UNEXPECTED_SECURE_FIELD = "unexpected_secure_field"


class ComplaintWorkflowError(ValueError):
    """Typed workflow error that never embeds draft content or protected values."""

    def __init__(self, code: WorkflowErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


ALLOWED_WORKFLOW_TRANSITIONS: dict[ComplaintWorkflowState, frozenset[ComplaintWorkflowState]] = {
    ComplaintWorkflowState.COLLECTING: frozenset(
        {
            ComplaintWorkflowState.CLARIFICATION_REQUIRED,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.REVIEW_READY,
            ComplaintWorkflowState.CANCELLED,
        }
    ),
    ComplaintWorkflowState.CLARIFICATION_REQUIRED: frozenset(
        {
            ComplaintWorkflowState.COLLECTING,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.REVIEW_READY,
            ComplaintWorkflowState.CANCELLED,
        }
    ),
    ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED: frozenset({ComplaintWorkflowState.CANCELLED}),
    ComplaintWorkflowState.REVIEW_READY: frozenset(
        {
            ComplaintWorkflowState.AWAITING_CONSENT,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.CANCELLED,
        }
    ),
    ComplaintWorkflowState.AWAITING_CONSENT: frozenset(
        {
            ComplaintWorkflowState.CONSENT_RECORDED,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.CANCELLED,
        }
    ),
    ComplaintWorkflowState.CONSENT_RECORDED: frozenset(
        {
            ComplaintWorkflowState.SUBMISSION_BLOCKED,
            ComplaintWorkflowState.CANCELLED,
        }
    ),
    ComplaintWorkflowState.SUBMISSION_BLOCKED: frozenset({ComplaintWorkflowState.CANCELLED}),
    ComplaintWorkflowState.CANCELLED: frozenset(),
}


class ComplaintWorkflowEngine:
    """Create and version governed drafts without API or persistence integration."""

    def create_draft(
        self,
        *,
        profile: RequirementsProfile,
        session_id: UUID,
        language: Language,
        applicant_type: ApplicantType,
        appeal_kind: AppealKind,
        category: Category,
        subcategory: ComplaintSubcategory,
        subject: str | None,
        issue_description: str | None,
        occurrence_details: dict[str, str],
        secure_references: list[SecureValueReference],
        privacy_notice_version: str,
        human_review_reasons: list[HandoffReason] | None = None,
        now: datetime | None = None,
    ) -> ComplaintWorkflowDraft:
        """Create one PII-screened provisional draft against a matching profile."""
        self._require_profile_match(
            profile=profile,
            applicant_type=applicant_type,
            appeal_kind=appeal_kind,
            category=category,
            subcategory=subcategory,
        )
        timestamp = now or datetime.now(UTC)
        return self._build(
            profile=profile,
            draft_id=uuid4(),
            session_id=session_id,
            language=language,
            applicant_type=applicant_type,
            appeal_kind=appeal_kind,
            category=category,
            subcategory=subcategory,
            subject=subject,
            issue_description=issue_description,
            occurrence_details=occurrence_details,
            secure_references=secure_references,
            privacy_notice_version=privacy_notice_version,
            human_review_reasons=human_review_reasons or [],
            version=1,
            consent_state=ConsentState.NOT_RECORDED,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def edit_draft(
        self,
        draft: ComplaintWorkflowDraft,
        *,
        profile: RequirementsProfile,
        applicant_type: ApplicantType | None = None,
        appeal_kind: AppealKind | None = None,
        category: Category | None = None,
        subcategory: ComplaintSubcategory | None = None,
        subject: str | None = None,
        issue_description: str | None = None,
        occurrence_details: dict[str, str] | None = None,
        secure_references: list[SecureValueReference] | None = None,
        human_review_reasons: list[HandoffReason] | None = None,
        now: datetime | None = None,
    ) -> ComplaintWorkflowDraft:
        """Create a new version and invalidate consent after any reviewed edit."""
        self._require_not_cancelled(draft)
        selected_applicant_type = applicant_type or draft.applicant_type
        selected_appeal_kind = appeal_kind or draft.appeal_kind
        selected_category = category or draft.category
        selected_subcategory = subcategory or draft.subcategory
        self._require_profile_match(
            profile=profile,
            applicant_type=selected_applicant_type,
            appeal_kind=selected_appeal_kind,
            category=selected_category,
            subcategory=selected_subcategory,
        )
        consent_state = (
            ConsentState.INVALIDATED
            if draft.consent_state in {ConsentState.RECORDED, ConsentState.INVALIDATED}
            else ConsentState.NOT_RECORDED
        )
        return self._build(
            profile=profile,
            draft_id=draft.draft_id,
            session_id=draft.session_id,
            language=draft.language,
            applicant_type=selected_applicant_type,
            appeal_kind=selected_appeal_kind,
            category=selected_category,
            subcategory=selected_subcategory,
            subject=draft.subject if subject is None else subject,
            issue_description=(
                draft.issue_description if issue_description is None else issue_description
            ),
            occurrence_details=(
                draft.occurrence_details if occurrence_details is None else occurrence_details
            ),
            secure_references=(
                draft.secure_references if secure_references is None else secure_references
            ),
            privacy_notice_version=draft.privacy_notice_version,
            human_review_reasons=(
                draft.human_review_reasons if human_review_reasons is None else human_review_reasons
            ),
            version=draft.version + 1,
            consent_state=consent_state,
            created_at=draft.created_at,
            updated_at=now or datetime.now(UTC),
        )

    def transition(
        self,
        draft: ComplaintWorkflowDraft,
        target: ComplaintWorkflowState,
        *,
        now: datetime | None = None,
    ) -> ComplaintWorkflowDraft:
        """Apply a central transition and its deterministic safety prerequisites."""
        self._require_not_cancelled(draft)
        if target not in ALLOWED_WORKFLOW_TRANSITIONS[draft.workflow_state]:
            raise ComplaintWorkflowError(WorkflowErrorCode.INVALID_TRANSITION)
        if target is ComplaintWorkflowState.REVIEW_READY:
            self._require_review_ready(draft)
        if target is ComplaintWorkflowState.AWAITING_CONSENT:
            self._require_review_ready(draft)
        if target is ComplaintWorkflowState.CONSENT_RECORDED:
            raise ComplaintWorkflowError(WorkflowErrorCode.CONSENT_REQUIRED)
        return _validated_copy(
            draft,
            workflow_state=target,
            updated_at=now or datetime.now(UTC),
        )

    def record_consent(
        self,
        draft: ComplaintWorkflowDraft,
        consent: ConsentBinding,
    ) -> ComplaintWorkflowDraft:
        """Bind consent to the exact current version, hash, notice, and language."""
        self._require_not_cancelled(draft)
        if draft.workflow_state is not ComplaintWorkflowState.AWAITING_CONSENT:
            raise ComplaintWorkflowError(WorkflowErrorCode.INVALID_TRANSITION)
        if consent.draft_id != draft.draft_id or consent.draft_version != draft.version:
            raise ComplaintWorkflowError(WorkflowErrorCode.STALE_CONSENT_VERSION)
        if consent.draft_hash != draft.draft_hash:
            raise ComplaintWorkflowError(WorkflowErrorCode.STALE_CONSENT_HASH)
        if consent.privacy_notice_version != draft.privacy_notice_version:
            raise ComplaintWorkflowError(WorkflowErrorCode.PRIVACY_NOTICE_MISMATCH)
        if consent.language is not draft.language:
            raise ComplaintWorkflowError(WorkflowErrorCode.CONSENT_LANGUAGE_MISMATCH)
        if consent.recorded_at < draft.updated_at:
            raise ComplaintWorkflowError(WorkflowErrorCode.CONSENT_TIMESTAMP_INVALID)
        return _validated_copy(
            draft,
            workflow_state=ComplaintWorkflowState.CONSENT_RECORDED,
            consent_state=ConsentState.RECORDED,
            updated_at=consent.recorded_at,
        )

    def block_submission(
        self,
        draft: ComplaintWorkflowDraft,
        *,
        now: datetime | None = None,
    ) -> ComplaintWorkflowDraft:
        """Terminate Stage 3A locally without contacting or implying an official system."""
        self._require_not_cancelled(draft)
        if draft.workflow_state is not ComplaintWorkflowState.CONSENT_RECORDED:
            raise ComplaintWorkflowError(WorkflowErrorCode.CONSENT_REQUIRED)
        return _validated_copy(
            draft,
            workflow_state=ComplaintWorkflowState.SUBMISSION_BLOCKED,
            updated_at=now or datetime.now(UTC),
        )

    @staticmethod
    def _require_review_ready(draft: ComplaintWorkflowDraft) -> None:
        if draft.missing_required_fields:
            raise ComplaintWorkflowError(WorkflowErrorCode.INCOMPLETE_DRAFT)
        if (
            draft.applicant_type is ApplicantType.UNKNOWN
            or draft.appeal_kind is AppealKind.UNKNOWN
            or draft.subcategory in {ComplaintSubcategory.UNKNOWN, ComplaintSubcategory.UNSUPPORTED}
        ):
            raise ComplaintWorkflowError(WorkflowErrorCode.CLARIFICATION_REQUIRED)
        if draft.human_review_status is HumanReviewStatus.REQUIRED:
            raise ComplaintWorkflowError(WorkflowErrorCode.HUMAN_REVIEW_REQUIRED)

    @staticmethod
    def _require_not_cancelled(draft: ComplaintWorkflowDraft) -> None:
        if draft.workflow_state is ComplaintWorkflowState.CANCELLED:
            raise ComplaintWorkflowError(WorkflowErrorCode.DRAFT_CANCELLED)

    @staticmethod
    def _require_profile_match(
        *,
        profile: RequirementsProfile,
        applicant_type: ApplicantType,
        appeal_kind: AppealKind,
        category: Category,
        subcategory: ComplaintSubcategory,
    ) -> None:
        if (
            (
                applicant_type is not ApplicantType.UNKNOWN
                and profile.applicant_type is not applicant_type
            )
            or (appeal_kind is not AppealKind.UNKNOWN and profile.appeal_kind is not appeal_kind)
            or profile.category is not category
            or (
                subcategory not in {ComplaintSubcategory.UNKNOWN, ComplaintSubcategory.UNSUPPORTED}
                and profile.subcategory is not subcategory
            )
        ):
            raise ComplaintWorkflowError(WorkflowErrorCode.PROFILE_MISMATCH)

    @staticmethod
    def _build(
        *,
        profile: RequirementsProfile,
        draft_id: UUID,
        session_id: UUID,
        language: Language,
        applicant_type: ApplicantType,
        appeal_kind: AppealKind,
        category: Category,
        subcategory: ComplaintSubcategory,
        subject: str | None,
        issue_description: str | None,
        occurrence_details: dict[str, str],
        secure_references: list[SecureValueReference],
        privacy_notice_version: str,
        human_review_reasons: list[HandoffReason],
        version: int,
        consent_state: ConsentState,
        created_at: datetime,
        updated_at: datetime,
    ) -> ComplaintWorkflowDraft:
        available: dict[str, str | None] = {
            **occurrence_details,
            "subject": subject,
            "issue_description": issue_description,
        }
        required_non_sensitive = list(profile.required_non_sensitive_fields)
        required_secure = list(profile.required_secure_fields)
        for conditional in profile.conditional_requirements:
            if available.get(conditional.when_field) == conditional.equals_value:
                required_non_sensitive.extend(conditional.required_non_sensitive_fields)
                required_secure.extend(conditional.required_secure_fields)
        provided_secure = {reference.field_type for reference in secure_references}
        missing = sorted(
            {
                *(field for field in required_non_sensitive if not available.get(field)),
                *(field.value for field in required_secure if field not in provided_secure),
            }
        )
        reasons = sorted(set(human_review_reasons), key=lambda reason: reason.value)
        if subcategory is ComplaintSubcategory.UNSUPPORTED:
            reasons = sorted(
                {*reasons, HandoffReason.UNSUPPORTED_CATEGORY},
                key=lambda reason: reason.value,
            )
        unexpected_secure = provided_secure - set(required_secure)
        if unexpected_secure:
            raise ComplaintWorkflowError(WorkflowErrorCode.UNEXPECTED_SECURE_FIELD)
        state = _initial_state(
            applicant_type=applicant_type,
            appeal_kind=appeal_kind,
            subcategory=subcategory,
            missing=missing,
            human_review_reasons=reasons,
        )
        values: dict[str, object] = {
            "draft_id": draft_id,
            "session_id": session_id,
            "language": language,
            "applicant_type": applicant_type,
            "appeal_kind": appeal_kind,
            "category": category,
            "subcategory": subcategory,
            "subject": subject,
            "issue_description": issue_description,
            "occurrence_details": occurrence_details,
            "secure_references": sorted(
                secure_references,
                key=lambda reference: (reference.field_type.value, str(reference.reference_id)),
            ),
            "missing_required_fields": missing,
            "human_review_status": (
                HumanReviewStatus.REQUIRED if reasons else HumanReviewStatus.NOT_REQUIRED
            ),
            "human_review_reasons": reasons,
            "workflow_state": state,
            "version": version,
            "created_at": created_at,
            "updated_at": updated_at,
            "requirements_profile_id": profile.profile_id,
            "requirements_profile_version": profile.profile_version,
            "privacy_notice_version": privacy_notice_version,
            "consent_state": consent_state,
        }
        values["draft_hash"] = canonical_draft_hash(values)
        return ComplaintWorkflowDraft.model_validate(values)


def _initial_state(
    *,
    applicant_type: ApplicantType,
    appeal_kind: AppealKind,
    subcategory: ComplaintSubcategory,
    missing: list[str],
    human_review_reasons: list[HandoffReason],
) -> ComplaintWorkflowState:
    if human_review_reasons:
        return ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED
    if (
        applicant_type is ApplicantType.UNKNOWN
        or appeal_kind is AppealKind.UNKNOWN
        or subcategory in {ComplaintSubcategory.UNKNOWN, ComplaintSubcategory.UNSUPPORTED}
    ):
        return ComplaintWorkflowState.CLARIFICATION_REQUIRED
    if missing:
        return ComplaintWorkflowState.COLLECTING
    return ComplaintWorkflowState.REVIEW_READY


def _validated_copy(
    draft: ComplaintWorkflowDraft,
    **updates: object,
) -> ComplaintWorkflowDraft:
    values = draft.model_dump(mode="python")
    values.update(updates)
    return ComplaintWorkflowDraft.model_validate(values)
