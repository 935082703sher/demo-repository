"""End-to-end deterministic Stage 3C local orchestration tests."""

from __future__ import annotations

import json
from dataclasses import asdict
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.errors import ConflictError
from app.domain.approval_evidence import assess_approval_metadata
from app.domain.complaint_orchestration import GovernedComplaintInput, OrchestrationOutcome
from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ComplaintWorkflowState,
    HandoffReason,
    HumanReviewStatus,
    OperatorQueueStatus,
    SecureFieldType,
)
from app.domain.enums import Category, Language
from app.domain.governance import ActivationStatus, ApprovalStatus
from app.domain.schemas import LLMRequest, LLMResult
from app.main import create_app
from app.services.complaint_drafts import ComplaintDraftService
from app.services.complaint_workflow import ALLOWED_WORKFLOW_TRANSITIONS
from app.services.complaint_workflow_adapter import GovernedComplaintWorkflowAdapter
from app.services.governed_complaint_orchestrator import GovernedComplaintOrchestrator
from evaluations.run_stage3c_scenarios import run_stage3c_scenarios


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        return LLMResult(text=request.passages[0], citations=request.source_ids)


def orchestrator() -> GovernedComplaintOrchestrator:
    adapter = GovernedComplaintWorkflowAdapter(
        legacy=ComplaintDraftService("demo-privacy-v1"),
        enabled=True,
        privacy_notice_version="demo-privacy-v1",
        consent_wording_version="synthetic-consent-v1",
    )
    return GovernedComplaintOrchestrator(
        adapter=adapter,
        privacy_notice_version="demo-privacy-v1",
        consent_wording_version="synthetic-consent-v1",
    )


def network_fields() -> dict[str, str]:
    return {
        "operator": "Synthetic Operator",
        "service_type": "synthetic_mobile_data",
        "region": "Synthetic Region",
        "district": "Synthetic City",
        "approximate_location": "Synthetic central zone",
        "event_time": "synthetic-time-window",
        "frequency": "synthetic recurring",
        "duration": "synthetic duration",
        "impact": "Synthetic service impact",
    }


def imei_fields() -> dict[str, str]:
    return {
        "request_kind": "synthetic_complaint",
        "action_attempted": "Synthetic action",
        "observed_result": "Synthetic result",
        "event_time": "synthetic-time-window",
    }


def test_state_transition_matrix_is_closed_and_exhaustive() -> None:
    expected = {
        ComplaintWorkflowState.COLLECTING: {
            ComplaintWorkflowState.CLARIFICATION_REQUIRED,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.REVIEW_READY,
            ComplaintWorkflowState.CANCELLED,
        },
        ComplaintWorkflowState.CLARIFICATION_REQUIRED: {
            ComplaintWorkflowState.COLLECTING,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.REVIEW_READY,
            ComplaintWorkflowState.CANCELLED,
        },
        ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED: {ComplaintWorkflowState.CANCELLED},
        ComplaintWorkflowState.REVIEW_READY: {
            ComplaintWorkflowState.AWAITING_CONSENT,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.CANCELLED,
        },
        ComplaintWorkflowState.AWAITING_CONSENT: {
            ComplaintWorkflowState.CONSENT_RECORDED,
            ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED,
            ComplaintWorkflowState.CANCELLED,
        },
        ComplaintWorkflowState.CONSENT_RECORDED: {
            ComplaintWorkflowState.SUBMISSION_BLOCKED,
            ComplaintWorkflowState.CANCELLED,
        },
        ComplaintWorkflowState.SUBMISSION_BLOCKED: {ComplaintWorkflowState.CANCELLED},
        ComplaintWorkflowState.CANCELLED: set(),
    }
    all_states = set(ComplaintWorkflowState)

    assert set(ALLOWED_WORKFLOW_TRANSITIONS) == all_states
    for source in ComplaintWorkflowState:
        permitted = set(ALLOWED_WORKFLOW_TRANSITIONS[source])
        prohibited = all_states - permitted
        assert permitted == expected[source]
        assert permitted.isdisjoint(prohibited)
        assert permitted | prohibited == all_states


def test_full_local_sequence_requires_exact_review_before_consent() -> None:
    service = orchestrator()
    session_id = uuid4()
    collecting = service.handle(
        GovernedComplaintInput(
            session_id=session_id,
            language=Language.EN,
            message="Synthetic individual network complaint",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.NETWORK_QUALITY,
            subcategory=ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            fields={"operator": "Synthetic Operator"},
        )
    )
    assert collecting.review is not None
    assert collecting.outcome is OrchestrationOutcome.COLLECTING

    clarification = service.handle(
        GovernedComplaintInput(
            session_id=session_id,
            draft_id=collecting.review.draft_id,
            expected_version=1,
            language=Language.EN,
            message="Synthetic network workflow",
            applicant_type=ApplicantType.NATURAL_PERSON,
            category=Category.NETWORK_QUALITY,
            subcategory=ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            fields={"service_type": "synthetic_mobile_data"},
        )
    )
    assert clarification.outcome is OrchestrationOutcome.CLARIFICATION
    assert clarification.review is not None

    recollecting = service.handle(
        GovernedComplaintInput(
            session_id=session_id,
            draft_id=clarification.review.draft_id,
            expected_version=2,
            language=Language.EN,
            message="Synthetic individual network complaint",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.NETWORK_QUALITY,
            subcategory=ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            fields={"region": "Synthetic Region"},
        )
    )
    assert recollecting.outcome is OrchestrationOutcome.COLLECTING
    assert recollecting.review is not None

    ready = service.handle(
        GovernedComplaintInput(
            session_id=session_id,
            draft_id=recollecting.review.draft_id,
            expected_version=3,
            language=Language.EN,
            message="Synthetic individual network complaint",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.NETWORK_QUALITY,
            subcategory=ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            fields=network_fields(),
        )
    )
    assert ready.outcome is OrchestrationOutcome.REVIEW_READY
    assert ready.review is not None
    with pytest.raises(ConflictError, match="Review the current"):
        service.consent(
            draft_id=ready.review.draft_id,
            version=ready.review.version,
            canonical_hash=ready.review.canonical_hash,
            idempotency_key="synthetic-consent-gate",
        )

    service.acknowledge_review(
        ready.review.draft_id,
        ready.review.version,
        ready.review.canonical_hash,
    )
    blocked, submission = service.consent(
        draft_id=ready.review.draft_id,
        version=ready.review.version,
        canonical_hash=ready.review.canonical_hash,
        idempotency_key="synthetic-consent-gate",
    )

    assert blocked.workflow_state is ComplaintWorkflowState.SUBMISSION_BLOCKED
    assert submission.officially_registered is False
    assert submission.case_number is None


@pytest.mark.parametrize(
    ("applicant_type", "appeal_kind"),
    [
        (ApplicantType.NATURAL_PERSON, AppealKind.APPLICATION),
        (ApplicantType.LEGAL_ENTITY, AppealKind.PROPOSAL),
        (ApplicantType.AUTHORIZED_REPRESENTATIVE, AppealKind.COMPLAINT),
    ],
)
def test_applicant_and_appeal_kind_are_independent(
    applicant_type: ApplicantType,
    appeal_kind: AppealKind,
) -> None:
    result = orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic IMEI workflow",
            applicant_type=applicant_type,
            appeal_kind=appeal_kind,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields=imei_fields(),
        )
    )

    assert result.review is not None
    assert result.review.applicant_type is applicant_type
    assert result.review.appeal_kind is appeal_kind
    assert result.review.category is Category.IMEI
    assert result.review.subcategory is ComplaintSubcategory.ERRORS_SUPPORT


def test_unknown_applicant_and_repeated_unclear_request_are_bounded() -> None:
    service = orchestrator()
    session = uuid4()
    first = service.handle(
        GovernedComplaintInput(
            session_id=session,
            language=Language.EN,
            message="Synthetic IMEI workflow",
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields={"request_kind": "synthetic_request"},
        )
    )
    second = service.handle(
        GovernedComplaintInput(
            session_id=session,
            draft_id=first.review.draft_id if first.review else None,
            expected_version=1,
            language=Language.EN,
            message="Synthetic IMEI workflow remains unclear",
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields={"action_attempted": "Synthetic action"},
        )
    )

    assert first.outcome is OrchestrationOutcome.CLARIFICATION
    assert second.outcome is OrchestrationOutcome.HUMAN_HANDOFF
    assert second.handoff is not None
    assert second.handoff.handoff.reason is HandoffReason.UNCLEAR_REQUEST


@pytest.mark.parametrize(
    ("category", "subcategory", "fields"),
    [
        (Category.IMEI, ComplaintSubcategory.ERRORS_SUPPORT, imei_fields()),
        (
            Category.MNP,
            ComplaintSubcategory.TRANSFER_CONDITIONS,
            {
                "request_kind": "synthetic_complaint",
                "current_stage": "synthetic stage",
                "operator": "Synthetic Operator",
                "submitted_at": "synthetic-time",
                "observed_error": "Synthetic error",
            },
        ),
        (
            Category.NUMBER_CODES,
            ComplaintSubcategory.NUMBER_CODE_INFORMATION,
            {
                "code_type": "synthetic city code",
                "country_or_region": "Synthetic Region",
                "request_kind": "synthetic application",
            },
        ),
        (
            Category.NETWORK_QUALITY,
            ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            network_fields(),
        ),
        (
            Category.WEBSITE_ISSUE,
            ComplaintSubcategory.WEBSITE_FUNCTIONAL_ERROR,
            {
                "page_url": "https://example.invalid/synthetic",
                "action_attempted": "Synthetic action",
                "error_message": "Synthetic error",
                "event_time": "synthetic-time",
                "device_type": "synthetic device",
                "browser_type": "synthetic browser",
            },
        ),
        (
            Category.OTHER,
            ComplaintSubcategory.OTHER_RTMCMATTER,
            {
                "description": "Synthetic RTMC matter",
                "desired_outcome": "Synthetic review",
            },
        ),
    ],
)
def test_every_supported_category_can_reach_non_official_review(
    category: Category,
    subcategory: ComplaintSubcategory,
    fields: dict[str, str],
) -> None:
    result = orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message=f"Synthetic individual complaint for {category.value}",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=category,
            subcategory=subcategory,
            fields=fields,
        )
    )

    assert result.outcome is OrchestrationOutcome.REVIEW_READY
    assert result.review is not None
    assert result.review.officially_registered is False
    assert result.review.case_number is None
    assert result.review.official_status is None


def test_final_review_is_complete_masked_and_contains_all_consent_metadata() -> None:
    service = orchestrator()
    reference = service.issue_synthetic_secure_reference(
        field_type=SecureFieldType.FULL_IMEI,
        synthetic_value=SecretStr("SYNTHETIC_TEST_VALUE_REVIEW"),
    )
    result = service.handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic individual IMEI complaint",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields=imei_fields(),
            required_secure_fields=[SecureFieldType.FULL_IMEI],
            secure_references=[reference],
        )
    )
    assert result.review is not None
    serialized = result.review.model_dump_json()

    assert result.review.missing_fields == []
    assert result.review.human_review_status is HumanReviewStatus.NOT_REQUIRED
    assert result.review.secure_reference_indicators[0].masked_display == "***"
    assert result.review.privacy_notice_version == "demo-privacy-v1"
    assert result.review.consent_wording_version == "synthetic-consent-v1"
    assert "not be officially registered" in result.review.not_officially_registered_notice
    assert "SYNTHETIC_TEST_VALUE_REVIEW" not in serialized


@pytest.mark.parametrize("language", list(Language))
def test_follow_up_questions_are_localized_versioned_and_one_at_a_time(
    language: Language,
) -> None:
    result = orchestrator().handle(
        GovernedComplaintInput(
            language=language,
            message="Synthetic mobile internet complaint",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.NETWORK_QUALITY,
            subcategory=ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            fields={"operator": "Synthetic Operator"},
        )
    )

    assert result.outcome is OrchestrationOutcome.COLLECTING
    assert result.follow_up_key is not None
    assert result.follow_up_key.startswith("synthetic-stage3c-follow-up-v1.")
    assert result.follow_up_question is not None
    assert "complete residential address" not in result.follow_up_question.casefold()


@pytest.mark.parametrize(
    ("message", "reason"),
    [
        ("This is an emergency", HandoffReason.EMERGENCY),
        ("I will kill someone", HandoffReason.THREAT_OR_VIOLENCE),
        ("I may kill myself", HandoffReason.SELF_HARM),
        ("My password is SYNTHETIC_TEST_VALUE", HandoffReason.SENSITIVE_PERSONAL_DATA),
        ("Interpret the law for me", HandoffReason.LEGAL_INTERPRETATION_REQUESTED),
        ("The official decision is wrong", HandoffReason.OFFICIAL_DECISION_DISPUTE),
        ("This is official misconduct", HandoffReason.MISCONDUCT_OR_CORRUPTION_ALLEGATION),
        ("RTMC credentials leaked", HandoffReason.SERIOUS_CYBERSECURITY_INCIDENT),
        ("My authority is unclear", HandoffReason.IDENTITY_OR_AUTHORITY_UNCLEAR),
        ("This concerns a vulnerable person", HandoffReason.MINOR_OR_VULNERABLE_PERSON),
        ("There is an unresolved source conflict", HandoffReason.SOURCE_CONFLICT),
        ("Approved information unavailable", HandoffReason.APPROVED_INFORMATION_UNAVAILABLE),
        ("I request human review", HandoffReason.MANUAL_REVIEW_REQUESTED),
    ],
)
def test_required_handoffs_are_typed_and_never_claim_a_queue(
    message: str,
    reason: HandoffReason,
) -> None:
    result = orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message=message,
            fields={"description": "Synthetic handoff scenario"},
        )
    )

    assert result.outcome is OrchestrationOutcome.HUMAN_HANDOFF
    assert result.handoff is not None
    assert result.handoff.handoff.reason is reason
    assert result.handoff.handoff.operator_queue_status is OperatorQueueStatus.NOT_CONFIGURED
    assert result.handoff.officially_registered is False
    assert result.handoff.case_number is None
    assert result.handoff.official_status is None


def test_human_review_draft_can_only_cancel_locally() -> None:
    service = orchestrator()
    handoff = service.handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic IMEI complaint requiring source review",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields=imei_fields(),
            human_review_reasons=[HandoffReason.SOURCE_CONFLICT],
        )
    )
    assert handoff.review is not None
    cancelled = service.cancel(handoff.review.draft_id)

    assert handoff.workflow_state is ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED
    assert cancelled.workflow_state is ComplaintWorkflowState.CANCELLED


def test_unsupported_subcategory_requires_handoff_and_never_official_state() -> None:
    result = orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic unsupported IMEI complaint",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.UNSUPPORTED,
            fields=imei_fields(),
        )
    )

    assert result.outcome is OrchestrationOutcome.HUMAN_HANDOFF
    assert result.handoff is not None
    assert result.handoff.handoff.reason is HandoffReason.UNSUPPORTED_CATEGORY
    assert result.officially_registered is False
    assert result.case_number is None
    assert result.official_status is None


def test_off_topic_request_preserves_existing_draft_and_provider_quota() -> None:
    provider = CountingProvider()
    app = create_app(provider=provider)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/complaints/draft",
            json={
                "language": "en",
                "category": "other",
                "fields": {"description": "Synthetic RTMC matter"},
            },
        ).json()["draft"]
        session_id = UUID(created["session_id"])
        before = app.state.usage_limits.snapshot(session_id)
        refusal = client.post(
            "/api/v1/chat",
            json={
                "session_id": str(session_id),
                "language": "en",
                "message": "Give me a recipe",
            },
        ).json()
        after = app.state.usage_limits.snapshot(session_id)
        preserved = client.get(f"/api/v1/complaints/{created['draft_id']}")

    assert refusal["response_type"] == "refusal"
    assert preserved.status_code == 200
    assert before.logical_requests == after.logical_requests == 0
    assert provider.calls == 0


def test_partial_named_approval_is_rejected_without_echoing_identity() -> None:
    supplied_name = "DJUMANOV XAYRULLA ABDULLADJANOVICH"
    result = assess_approval_metadata(
        {
            "approver_name": supplied_name,
            "approver_role": (
                "Jismoniy va yuridik shaxslar murojaatlari bilan ishlash bo'limi boshlig'i"
            ),
        }
    )
    serialized = result.model_dump_json()

    assert result.accepted is False
    assert result.approval_status is ApprovalStatus.PENDING_REVIEW
    assert result.activation_status is ActivationStatus.INACTIVE
    assert result.runtime_eligible is False
    assert supplied_name not in serialized
    assert {
        "approval_reference",
        "target_type",
        "target_id",
        "target_version",
        "content_hash",
        "language",
        "approval_date",
        "effective_date",
        "review_or_expiry_date",
        "source_document_reference",
    } <= set(result.missing_fields)


def test_scenario_runner_has_twelve_synthetic_safe_results() -> None:
    rows = run_stage3c_scenarios()
    serialized = json.dumps([asdict(row) for row in rows], default=str)

    assert len(rows) == 12
    assert all(row.passed for row in rows)
    assert all(not row.officially_registered for row in rows)
    assert all(row.case_number is None and row.official_status is None for row in rows)
    assert "SYNTHETIC_TEST_VALUE" not in serialized


def test_feature_disabled_keeps_legacy_and_enabled_adds_no_openapi_paths() -> None:
    disabled = create_app(settings=Settings(_env_file=None, environment="test"))
    enabled = create_app(
        settings=Settings(
            _env_file=None,
            environment="test",
            governed_complaint_workflow_enabled=True,
        )
    )

    assert disabled.state.governed_complaint_orchestrator is None
    assert enabled.state.governed_complaint_orchestrator is not None
    assert disabled.openapi() == enabled.openapi()
    # 5 legacy + 8 /assistant (incl. /understand, /converse, /converse/stream)
    # + 2 diagnostics + admin.
    assert len(enabled.openapi()["paths"]) == 16
