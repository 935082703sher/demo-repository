"""Stage 3A typed complaint-workflow and state-machine tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ComplaintWorkflowDraft,
    ComplaintWorkflowState,
    ConditionalRequirement,
    ConsentBinding,
    ConsentState,
    HandoffReason,
    LegalReviewStatus,
    ProfileSourceReference,
    RequirementsProfile,
    SecureFieldType,
    SecureValueReference,
)
from app.domain.enums import Category, Language
from app.domain.governance import ApprovalStatus
from app.services.complaint_workflow import (
    ALLOWED_WORKFLOW_TRANSITIONS,
    ComplaintWorkflowEngine,
    ComplaintWorkflowError,
    WorkflowErrorCode,
)
from app.services.secure_values import SyntheticSecureValueIssuer

NOW = datetime(2026, 8, 11, 12, tzinfo=UTC)
SESSION_ID = UUID("10000000-0000-4000-8000-000000000001")


def profile(
    *,
    applicant_type: ApplicantType = ApplicantType.NATURAL_PERSON,
    appeal_kind: AppealKind = AppealKind.COMPLAINT,
    category: Category = Category.IMEI,
    subcategory: ComplaintSubcategory = ComplaintSubcategory.ERRORS_SUPPORT,
) -> RequirementsProfile:
    secure_field = (
        SecureFieldType.LEGAL_ENTITY_REGISTRATION_ID
        if applicant_type is ApplicantType.LEGAL_ENTITY
        else SecureFieldType.FULL_IMEI
    )
    return RequirementsProfile(
        profile_id="SYNTHETIC-PROFILE-STAGE3A-001",
        profile_version=1,
        effective_date=date(2026, 8, 11),
        applicant_type=applicant_type,
        appeal_kind=appeal_kind,
        category=category,
        subcategory=subcategory,
        required_non_sensitive_fields=["subject", "issue_description", "event_time"],
        required_secure_fields=[secure_field],
        prohibited_from_ordinary_storage=[secure_field],
        approval_status=ApprovalStatus.PENDING_REVIEW,
        legal_review_status=LegalReviewStatus.PENDING_REVIEW,
        owner_role="Synthetic RTMC workflow owner",
        source_references=[
            ProfileSourceReference(
                source_id="SYNTHETIC-STAGE3A-DESIGN-001",
                source_version=1,
            )
        ],
        production_eligible=False,
        provisional=True,
    )


def secure_reference(
    field_type: SecureFieldType = SecureFieldType.FULL_IMEI,
) -> SecureValueReference:
    return SyntheticSecureValueIssuer().issue_reference(
        field_type=field_type,
        synthetic_value=SecretStr("SYNTHETIC_TEST_VALUE_ALPHA"),
    )


def complete_draft(
    *,
    engine: ComplaintWorkflowEngine | None = None,
    requirements: RequirementsProfile | None = None,
    applicant_type: ApplicantType = ApplicantType.NATURAL_PERSON,
    appeal_kind: AppealKind = AppealKind.COMPLAINT,
    human_review_reasons: list[HandoffReason] | None = None,
) -> ComplaintWorkflowDraft:
    workflow = engine or ComplaintWorkflowEngine()
    selected_profile = requirements or profile(
        applicant_type=applicant_type,
        appeal_kind=appeal_kind,
    )
    required_secure_type = selected_profile.required_secure_fields[0]
    return workflow.create_draft(
        profile=selected_profile,
        session_id=SESSION_ID,
        language=Language.EN,
        applicant_type=applicant_type,
        appeal_kind=appeal_kind,
        category=selected_profile.category,
        subcategory=selected_profile.subcategory,
        subject="Synthetic device issue",
        issue_description="Synthetic test description with no personal data",
        occurrence_details={"event_time": "synthetic-time-window"},
        secure_references=[secure_reference(required_secure_type)],
        privacy_notice_version="synthetic-notice-v1",
        human_review_reasons=human_review_reasons,
        now=NOW,
    )


def consent_for(draft: ComplaintWorkflowDraft, **changes: object) -> ConsentBinding:
    values: dict[str, object] = {
        "draft_id": draft.draft_id,
        "draft_version": draft.version,
        "draft_hash": draft.draft_hash,
        "privacy_notice_version": draft.privacy_notice_version,
        "language": draft.language,
        "consent_given": True,
        "recorded_at": NOW + timedelta(minutes=1),
    }
    values.update(changes)
    return ConsentBinding.model_validate(values)


def test_applicant_appeal_kind_and_category_are_independent() -> None:
    application = profile(appeal_kind=AppealKind.APPLICATION)
    complaint = profile(appeal_kind=AppealKind.COMPLAINT)
    legal_entity = profile(applicant_type=ApplicantType.LEGAL_ENTITY)

    assert application.category is complaint.category is Category.IMEI
    assert application.appeal_kind is not complaint.appeal_kind
    assert legal_entity.applicant_type is ApplicantType.LEGAL_ENTITY
    assert legal_entity.appeal_kind is AppealKind.COMPLAINT


def test_natural_person_and_legal_entity_profiles_cannot_be_mixed() -> None:
    engine = ComplaintWorkflowEngine()
    legal_profile = profile(applicant_type=ApplicantType.LEGAL_ENTITY)

    with pytest.raises(ComplaintWorkflowError) as error:
        complete_draft(
            engine=engine,
            requirements=legal_profile,
            applicant_type=ApplicantType.NATURAL_PERSON,
        )

    assert error.value.code is WorkflowErrorCode.PROFILE_MISMATCH


@pytest.mark.parametrize(
    ("applicant_type", "appeal_kind", "subcategory"),
    [
        (ApplicantType.UNKNOWN, AppealKind.COMPLAINT, ComplaintSubcategory.ERRORS_SUPPORT),
        (ApplicantType.NATURAL_PERSON, AppealKind.UNKNOWN, ComplaintSubcategory.ERRORS_SUPPORT),
        (ApplicantType.NATURAL_PERSON, AppealKind.COMPLAINT, ComplaintSubcategory.UNKNOWN),
    ],
)
def test_unknown_classification_requires_clarification(
    applicant_type: ApplicantType,
    appeal_kind: AppealKind,
    subcategory: ComplaintSubcategory,
) -> None:
    engine = ComplaintWorkflowEngine()
    requirements = profile()
    draft = engine.create_draft(
        profile=requirements,
        session_id=SESSION_ID,
        language=Language.EN,
        applicant_type=applicant_type,
        appeal_kind=appeal_kind,
        category=Category.IMEI,
        subcategory=subcategory,
        subject="Synthetic issue",
        issue_description="Synthetic description",
        occurrence_details={"event_time": "synthetic-time"},
        secure_references=[secure_reference()],
        privacy_notice_version="synthetic-notice-v1",
        now=NOW,
    )

    assert draft.workflow_state is ComplaintWorkflowState.CLARIFICATION_REQUIRED


def test_clarification_is_recorded_as_a_new_version() -> None:
    engine = ComplaintWorkflowEngine()
    requirements = profile()
    unknown = engine.create_draft(
        profile=requirements,
        session_id=SESSION_ID,
        language=Language.EN,
        applicant_type=ApplicantType.UNKNOWN,
        appeal_kind=AppealKind.UNKNOWN,
        category=Category.IMEI,
        subcategory=ComplaintSubcategory.UNKNOWN,
        subject="Synthetic issue",
        issue_description="Synthetic description",
        occurrence_details={"event_time": "synthetic-time"},
        secure_references=[secure_reference()],
        privacy_notice_version="synthetic-notice-v1",
        now=NOW,
    )

    clarified = engine.edit_draft(
        unknown,
        profile=requirements,
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=AppealKind.COMPLAINT,
        subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
        now=NOW + timedelta(minutes=1),
    )

    assert clarified.version == 2
    assert clarified.draft_hash != unknown.draft_hash
    assert clarified.workflow_state is ComplaintWorkflowState.REVIEW_READY


def test_provisional_profile_cannot_be_marked_approved_or_production_eligible() -> None:
    values = profile().model_dump(mode="python")
    values["approval_status"] = ApprovalStatus.APPROVED
    with pytest.raises(ValidationError, match="pending review"):
        RequirementsProfile.model_validate(values)

    values = profile().model_dump(mode="python")
    values["production_eligible"] = True
    with pytest.raises(ValidationError):
        RequirementsProfile.model_validate(values)


def test_conditional_secure_requirement_must_share_ordinary_storage_prohibition() -> None:
    values = profile().model_dump(mode="python")
    values["conditional_requirements"] = [
        ConditionalRequirement(
            when_field="request_mode",
            equals_value="synthetic-representative",
            required_secure_fields=[SecureFieldType.REPRESENTATIVE_AUTHORIZATION],
        )
    ]

    with pytest.raises(ValidationError, match="prohibited from ordinary storage"):
        RequirementsProfile.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issue_description", "phone: +998 90 123 45 67"),
        ("issue_description", "passport: AB 1234567"),
    ],
)
def test_raw_sensitive_values_are_rejected_by_ordinary_draft_model(
    field: str,
    value: str,
) -> None:
    values = complete_draft().model_dump(mode="python")
    values[field] = value

    with pytest.raises(ValidationError, match="sensitive data"):
        ComplaintWorkflowDraft.model_validate(values)


@pytest.mark.parametrize("field_name", ["full_imei", "passport_number", "private_phone"])
def test_sensitive_field_names_are_rejected_from_occurrence_details(
    field_name: str,
) -> None:
    engine = ComplaintWorkflowEngine()
    requirements = profile()

    with pytest.raises(ValidationError, match="protected data"):
        engine.create_draft(
            profile=requirements,
            session_id=SESSION_ID,
            language=Language.EN,
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            subject="Synthetic issue",
            issue_description="Synthetic description",
            occurrence_details={field_name: "SYNTHETIC_TEST_VALUE"},
            secure_references=[secure_reference()],
            privacy_notice_version="synthetic-notice-v1",
            now=NOW,
        )


def test_incomplete_draft_cannot_move_to_review_ready() -> None:
    engine = ComplaintWorkflowEngine()
    requirements = profile()
    draft = engine.create_draft(
        profile=requirements,
        session_id=SESSION_ID,
        language=Language.EN,
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=AppealKind.COMPLAINT,
        category=Category.IMEI,
        subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
        subject="Synthetic issue",
        issue_description=None,
        occurrence_details={},
        secure_references=[],
        privacy_notice_version="synthetic-notice-v1",
        now=NOW,
    )

    assert draft.workflow_state is ComplaintWorkflowState.COLLECTING
    assert {"issue_description", "event_time", "full_imei"} <= set(draft.missing_required_fields)
    with pytest.raises(ComplaintWorkflowError) as error:
        engine.transition(draft, ComplaintWorkflowState.REVIEW_READY, now=NOW)
    assert error.value.code is WorkflowErrorCode.INCOMPLETE_DRAFT

    direct_values = draft.model_dump(mode="python")
    direct_values["workflow_state"] = ComplaintWorkflowState.AWAITING_CONSENT
    with pytest.raises(ValidationError, match="advanced draft state"):
        ComplaintWorkflowDraft.model_validate(direct_values)


def test_canonical_hash_ignores_mapping_order_and_insignificant_whitespace() -> None:
    engine = ComplaintWorkflowEngine()
    requirements = profile()
    reference = secure_reference()
    first = engine.create_draft(
        profile=requirements,
        session_id=SESSION_ID,
        language=Language.EN,
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=AppealKind.COMPLAINT,
        category=Category.IMEI,
        subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
        subject="Synthetic issue",
        issue_description="Synthetic description",
        occurrence_details={"event_time": "synthetic time", "impact": "synthetic impact"},
        secure_references=[reference],
        privacy_notice_version="synthetic-notice-v1",
        now=NOW,
    )
    second = engine.create_draft(
        profile=requirements,
        session_id=SESSION_ID,
        language=Language.EN,
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=AppealKind.COMPLAINT,
        category=Category.IMEI,
        subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
        subject="  Synthetic   issue ",
        issue_description="Synthetic   description",
        occurrence_details={"impact": "synthetic  impact", "event_time": "synthetic time"},
        secure_references=[reference],
        privacy_notice_version="synthetic-notice-v1",
        now=NOW,
    )

    assert first.draft_hash == second.draft_hash


def test_edit_creates_version_and_hash_and_invalidates_consent() -> None:
    engine = ComplaintWorkflowEngine()
    requirements = profile()
    ready = complete_draft(engine=engine, requirements=requirements)
    awaiting = engine.transition(ready, ComplaintWorkflowState.AWAITING_CONSENT, now=NOW)
    consented = engine.record_consent(awaiting, consent_for(awaiting))

    with pytest.raises(ComplaintWorkflowError) as transition_error:
        engine.transition(consented, ComplaintWorkflowState.COLLECTING, now=NOW)
    assert transition_error.value.code is WorkflowErrorCode.INVALID_TRANSITION

    edited = engine.edit_draft(
        consented,
        profile=requirements,
        issue_description="Changed synthetic description",
        now=NOW + timedelta(minutes=2),
    )

    assert edited.version == consented.version + 1
    assert edited.draft_hash != consented.draft_hash
    assert edited.consent_state is ConsentState.INVALIDATED
    assert edited.workflow_state is ComplaintWorkflowState.REVIEW_READY


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"draft_version": 2}, WorkflowErrorCode.STALE_CONSENT_VERSION),
        ({"draft_hash": "0" * 64}, WorkflowErrorCode.STALE_CONSENT_HASH),
        (
            {"privacy_notice_version": "synthetic-old-notice"},
            WorkflowErrorCode.PRIVACY_NOTICE_MISMATCH,
        ),
        ({"language": Language.RU}, WorkflowErrorCode.CONSENT_LANGUAGE_MISMATCH),
        (
            {"recorded_at": NOW - timedelta(seconds=1)},
            WorkflowErrorCode.CONSENT_TIMESTAMP_INVALID,
        ),
    ],
)
def test_consent_rejects_stale_or_mismatched_binding(
    change: dict[str, object],
    expected: WorkflowErrorCode,
) -> None:
    engine = ComplaintWorkflowEngine()
    draft = engine.transition(
        complete_draft(engine=engine),
        ComplaintWorkflowState.AWAITING_CONSENT,
        now=NOW,
    )

    with pytest.raises(ComplaintWorkflowError) as error:
        engine.record_consent(draft, consent_for(draft, **change))

    assert error.value.code is expected
    assert str(error.value) == expected.value


def test_human_review_trigger_stops_automatic_progression() -> None:
    engine = ComplaintWorkflowEngine()
    draft = complete_draft(
        engine=engine,
        human_review_reasons=[HandoffReason.LEGAL_INTERPRETATION_REQUESTED],
    )

    assert draft.workflow_state is ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED
    with pytest.raises(ComplaintWorkflowError) as error:
        engine.transition(draft, ComplaintWorkflowState.REVIEW_READY, now=NOW)
    assert error.value.code is WorkflowErrorCode.INVALID_TRANSITION


def test_unsupported_subcategory_is_preserved_and_requires_human_review() -> None:
    engine = ComplaintWorkflowEngine()
    requirements = profile()
    draft = engine.create_draft(
        profile=requirements,
        session_id=SESSION_ID,
        language=Language.EN,
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=AppealKind.COMPLAINT,
        category=Category.IMEI,
        subcategory=ComplaintSubcategory.UNSUPPORTED,
        subject="Synthetic issue",
        issue_description="Synthetic description",
        occurrence_details={"event_time": "synthetic-time"},
        secure_references=[secure_reference()],
        privacy_notice_version="synthetic-notice-v1",
        now=NOW,
    )

    assert draft.subcategory is ComplaintSubcategory.UNSUPPORTED
    assert draft.workflow_state is ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED
    assert HandoffReason.UNSUPPORTED_CATEGORY in draft.human_review_reasons


def test_stage3a_ends_at_submission_blocked_without_official_state() -> None:
    engine = ComplaintWorkflowEngine()
    ready = complete_draft(engine=engine)
    awaiting = engine.transition(ready, ComplaintWorkflowState.AWAITING_CONSENT, now=NOW)
    recorded = engine.record_consent(awaiting, consent_for(awaiting))
    blocked = engine.block_submission(recorded, now=NOW + timedelta(minutes=2))

    assert blocked.workflow_state is ComplaintWorkflowState.SUBMISSION_BLOCKED
    forbidden = {"registered", "accepted", "assigned", "resolved", "official"}
    assert not any(token in state.value for state in ComplaintWorkflowState for token in forbidden)
    assert not any(
        field in ComplaintWorkflowDraft.model_fields
        for field in ("case_number", "official_status", "responsible_department", "legal_decision")
    )


def test_invalid_transition_and_cancelled_terminal_fail_safely() -> None:
    engine = ComplaintWorkflowEngine()
    ready = complete_draft(engine=engine)
    with pytest.raises(ComplaintWorkflowError) as error:
        engine.transition(ready, ComplaintWorkflowState.SUBMISSION_BLOCKED, now=NOW)
    assert error.value.code is WorkflowErrorCode.INVALID_TRANSITION

    cancelled = engine.transition(ready, ComplaintWorkflowState.CANCELLED, now=NOW)
    assert ALLOWED_WORKFLOW_TRANSITIONS[ComplaintWorkflowState.CANCELLED] == frozenset()
    with pytest.raises(ComplaintWorkflowError) as error:
        engine.block_submission(cancelled, now=NOW)
    assert error.value.code is WorkflowErrorCode.DRAFT_CANCELLED
