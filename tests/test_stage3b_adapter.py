"""Stage 3B governed adapter, consent, privacy, and compatibility tests."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.errors import ConflictError, RequestValidationError
from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ComplaintWorkflowState,
    ConsentState,
    HandoffReason,
    OperatorQueueStatus,
    SecureFieldType,
    SecureValueReference,
)
from app.domain.enums import Category, EscalationReason, Language
from app.domain.schemas import DraftUpsertRequest, LLMRequest, LLMResult, SubmitRequest
from app.main import create_app
from app.services.complaint_drafts import ComplaintDraftService
from app.services.complaint_workflow_adapter import (
    GovernedComplaintWorkflowAdapter,
    GovernedMappingContext,
)


class NoCallProvider:
    """Provider double used to prove deterministic refusals never generate."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResult:
        self.calls += 1
        return LLMResult(text=request.passages[0], citations=request.source_ids)


def adapter(*, enabled: bool = True) -> GovernedComplaintWorkflowAdapter:
    legacy = ComplaintDraftService("demo-privacy-v1")
    return GovernedComplaintWorkflowAdapter(
        legacy=legacy,
        enabled=enabled,
        privacy_notice_version="demo-privacy-v1",
        consent_wording_version="synthetic-consent-v1",
    )


def imei_fields(**updates: str) -> dict[str, str]:
    fields = {
        "request_kind": "complaint",
        "action_attempted": "Synthetic status check",
        "observed_result": "Synthetic error shown",
        "event_time": "synthetic-time-window",
    }
    fields.update(updates)
    return fields


def explicit_mapping(
    *, secure: bool = False, appeal_kind: AppealKind = AppealKind.COMPLAINT
) -> GovernedMappingContext:
    service = adapter()
    references: tuple[SecureValueReference, ...] = ()
    required: tuple[SecureFieldType, ...] = ()
    if secure:
        required = (SecureFieldType.FULL_IMEI,)
        references = (
            service.issue_synthetic_secure_reference(
                field_type=SecureFieldType.FULL_IMEI,
                synthetic_value=SecretStr("SYNTHETIC_TEST_VALUE_ADAPTER"),
            ),
        )
    return GovernedMappingContext(
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=appeal_kind,
        subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
        required_secure_fields=required,
        secure_references=references,
    )


def create_complete(
    service: GovernedComplaintWorkflowAdapter,
    *,
    mapping: GovernedMappingContext | None = None,
) -> tuple[UUID, int]:
    review = service.upsert_governed(
        DraftUpsertRequest(
            language=Language.EN,
            category=Category.IMEI,
            fields=imei_fields(),
        ),
        mapping=mapping or explicit_mapping(),
    )
    assert review.complete
    return review.draft_id, review.version


def test_feature_flag_defaults_disabled_and_rejects_unsafe_enablement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOVERNED_COMPLAINT_WORKFLOW_ENABLED", raising=False)
    assert Settings(_env_file=None).governed_complaint_workflow_enabled is False

    with pytest.raises(ValidationError, match="local/test"):
        Settings(
            _env_file=None,
            environment="production",
            governed_complaint_workflow_enabled=True,
        )
    with pytest.raises(ValidationError, match="mock provider"):
        Settings(
            _env_file=None,
            environment="test",
            governed_complaint_workflow_enabled=True,
            llm_provider="openai",
        )
    monkeypatch.setenv("GOVERNED_COMPLAINT_WORKFLOW_ENABLED", "unknown")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_disabled_adapter_preserves_legacy_review_exactly() -> None:
    request = DraftUpsertRequest(
        language=Language.EN,
        category=Category.IMEI,
        fields=imei_fields(),
    )
    review = adapter(enabled=False).upsert(request)

    assert review.complete
    assert review.fields_missing == []
    assert len(review.draft_hash) == 64


def test_enabled_public_mapping_fails_closed_on_ambiguous_classifications() -> None:
    review = adapter().upsert(
        DraftUpsertRequest(
            language=Language.EN,
            category=Category.IMEI,
            fields=imei_fields(),
        )
    )

    assert not review.complete
    assert {"applicant_type", "appeal_kind", "subcategory"} <= set(review.fields_missing)


def test_explicit_adapter_mapping_preserves_version_hash_and_legacy_fields() -> None:
    service = adapter()
    mapping = explicit_mapping(appeal_kind=AppealKind.APPLICATION)
    created = service.upsert_governed(
        DraftUpsertRequest(
            language=Language.EN,
            category=Category.IMEI,
            fields=imei_fields(),
        ),
        mapping=mapping,
    )
    governed = service.get_governed(created.draft_id)

    assert created.version == governed.version == 1
    assert created.draft_hash == governed.draft_hash
    assert created.fields == imei_fields()
    assert governed.applicant_type is ApplicantType.NATURAL_PERSON
    assert governed.appeal_kind is AppealKind.APPLICATION
    assert governed.category is Category.IMEI
    assert governed.workflow_state is ComplaintWorkflowState.REVIEW_READY


def test_missing_field_and_secure_reference_progression() -> None:
    service = adapter()
    missing_secure = GovernedMappingContext(
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=AppealKind.COMPLAINT,
        subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
        required_secure_fields=(SecureFieldType.FULL_IMEI,),
    )
    created = service.upsert_governed(
        DraftUpsertRequest(
            language=Language.EN,
            category=Category.IMEI,
            fields={"request_kind": "complaint"},
        ),
        mapping=missing_secure,
    )
    reference = service.issue_synthetic_secure_reference(
        field_type=SecureFieldType.FULL_IMEI,
        synthetic_value=SecretStr("SYNTHETIC_TEST_VALUE_PROGRESS"),
    )
    completed_mapping = GovernedMappingContext(
        applicant_type=ApplicantType.NATURAL_PERSON,
        appeal_kind=AppealKind.COMPLAINT,
        subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
        required_secure_fields=(SecureFieldType.FULL_IMEI,),
        secure_references=(reference,),
    )
    updated = service.upsert_governed(
        DraftUpsertRequest(
            draft_id=created.draft_id,
            expected_version=1,
            language=Language.EN,
            category=Category.IMEI,
            fields=imei_fields(),
        ),
        mapping=completed_mapping,
    )

    assert "full_imei" in created.fields_missing
    assert updated.version == 2
    assert updated.complete
    assert updated.personal_data_to_submit == ["full_imei"]
    serialized = service.get_governed(updated.draft_id).model_dump_json()
    assert "SYNTHETIC_TEST_VALUE_PROGRESS" not in serialized
    assert '"masked_display":"***"' in serialized


def test_deterministic_hash_ignores_record_identity_and_time() -> None:
    service = adapter()
    first_id, _ = create_complete(service)
    second_id, _ = create_complete(service)

    assert first_id != second_id
    assert service.get_governed(first_id).draft_hash == service.get_governed(second_id).draft_hash


def test_consent_is_fully_bound_and_stops_at_submission_blocked() -> None:
    service = adapter()
    draft_id, version = create_complete(service)
    response = service.submit(
        draft_id,
        SubmitRequest(
            consent=True,
            draft_version=version,
            privacy_notice_version="demo-privacy-v1",
            idempotency_key="synthetic-submit-1",
        ),
        uuid4(),
    )
    governed = service.get_governed(draft_id)
    consent = service.consent_binding(draft_id, version)

    assert governed.workflow_state is ComplaintWorkflowState.SUBMISSION_BLOCKED
    assert governed.consent_state is ConsentState.RECORDED
    assert consent is not None
    assert consent.draft_hash == governed.draft_hash
    assert consent.language is governed.language
    assert consent.privacy_notice_version == "demo-privacy-v1"
    assert consent.consent_wording_version == "synthetic-consent-v1"
    assert response.success is False
    assert response.officially_registered is False
    assert response.case_number is None


def test_material_edit_invalidates_consent_and_rejects_stale_submit() -> None:
    service = adapter()
    mapping = explicit_mapping()
    draft_id, version = create_complete(service, mapping=mapping)
    service.submit(
        draft_id,
        SubmitRequest(
            consent=True,
            draft_version=version,
            privacy_notice_version="demo-privacy-v1",
            idempotency_key="synthetic-submit-2",
        ),
        uuid4(),
    )
    edited = service.upsert_governed(
        DraftUpsertRequest(
            draft_id=draft_id,
            expected_version=version,
            language=Language.EN,
            category=Category.IMEI,
            fields={"observed_result": "A different synthetic result"},
        ),
        mapping=mapping,
    )

    assert service.get_governed(draft_id).consent_state is ConsentState.INVALIDATED
    assert edited.version == version + 1
    with pytest.raises(ConflictError) as error:
        service.submit(
            draft_id,
            SubmitRequest(
                consent=True,
                draft_version=version,
                privacy_notice_version="demo-privacy-v1",
                idempotency_key="synthetic-submit-3",
            ),
            uuid4(),
        )
    assert error.value.code == "stale_draft_version"


def test_raw_pii_is_absent_from_errors_and_idempotency_is_screened() -> None:
    service = adapter()
    raw = "+998 90 123 45 67"
    with pytest.raises(RequestValidationError) as draft_error:
        service.upsert_governed(
            DraftUpsertRequest(
                language=Language.EN,
                category=Category.IMEI,
                fields=imei_fields(observed_result=f"phone: {raw}"),
            ),
            mapping=explicit_mapping(),
        )
    assert raw not in str(draft_error.value)

    draft_id, version = create_complete(service)
    with pytest.raises(RequestValidationError) as submit_error:
        service.submit(
            draft_id,
            SubmitRequest(
                consent=True,
                draft_version=version,
                privacy_notice_version="demo-privacy-v1",
                idempotency_key="123456789012345",
            ),
            uuid4(),
        )
    assert submit_error.value.code == "unsafe_idempotency_key"
    assert "123456789012345" not in str(submit_error.value)


def test_every_legacy_handoff_reason_maps_without_losing_legacy_code() -> None:
    service = adapter()
    for reason in EscalationReason:
        session_id = uuid4()
        service.observe_legacy_handoff(session_id, Language.EN, reason, uuid4())
        handoff = service.last_handoff(session_id)
        assert handoff is not None
        assert isinstance(handoff.reason, HandoffReason)
        assert reason.value in handoff.safe_summary
        assert handoff.operator_queue_status is OperatorQueueStatus.NOT_CONFIGURED


def test_feature_flag_does_not_change_openapi_or_add_client_control() -> None:
    disabled = create_app(settings=Settings(_env_file=None, environment="test"))
    enabled = create_app(
        settings=Settings(
            _env_file=None,
            environment="test",
            governed_complaint_workflow_enabled=True,
        )
    )

    assert disabled.openapi() == enabled.openapi()
    serialized = str(enabled.openapi())
    assert "governed_complaint_workflow_enabled" not in serialized
    assert "GOVERNED_COMPLAINT_WORKFLOW_ENABLED" not in serialized


def test_enabled_chat_handoff_is_internal_typed_and_queue_not_configured() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        governed_complaint_workflow_enabled=True,
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "I want a human operator"},
        ).json()
    workflow = app.state.governed_complaint_workflow
    handoff = workflow.last_handoff(UUID(response["session_id"]))

    assert response["handoff_reason"] == EscalationReason.CITIZEN_REQUEST.value
    assert handoff is not None
    assert handoff.reason is HandoffReason.MANUAL_REVIEW_REQUESTED
    assert handoff.operator_queue_status is OperatorQueueStatus.NOT_CONFIGURED


def test_religion_refusal_does_not_call_provider_or_destroy_draft() -> None:
    provider = NoCallProvider()
    app = create_app(provider=provider)
    with TestClient(app) as client:
        draft = client.post(
            "/api/v1/complaints/draft",
            json={
                "language": "en",
                "category": "other",
                "fields": {"description": "Synthetic matter"},
            },
        ).json()["draft"]
        refused = client.post(
            "/api/v1/chat",
            json={
                "session_id": draft["session_id"],
                "language": "en",
                "message": "Tell me about religious history",
            },
        ).json()
        resumed = client.post(
            "/api/v1/chat",
            json={
                "session_id": draft["session_id"],
                "language": "en",
                "message": "Internet is slow in Samarqand region",
            },
        ).json()
        existing = client.get(f"/api/v1/complaints/{draft['draft_id']}")

    assert refused["response_type"] == "refusal"
    assert resumed["category"] == "network_quality"
    assert existing.status_code == 200
    assert provider.calls == 0


@pytest.mark.parametrize(
    ("language", "message"),
    [
        ("en", "Internet is slow in Samarqand region"),
        ("uz", "Samarqand viloyatida mobil internet sekin"),
        ("ru", "В Самаркандской области плохо работает мобильный интернет"),
    ],
)
def test_required_region_examples_reach_network_quality(language: str, message: str) -> None:
    with TestClient(create_app()) as client:
        body = client.post(
            "/api/v1/chat",
            json={"language": language, "message": message},
        ).json()

    assert body["response_type"] != "refusal"
    assert body["category"] == Category.NETWORK_QUALITY.value


def test_ambiguous_religion_region_typo_gets_one_clarification_then_handoff() -> None:
    with TestClient(create_app()) as client:
        first = client.post(
            "/api/v1/chat",
            json={"language": "en", "message": "Is this relegion or region?"},
        ).json()
        second = client.post(
            "/api/v1/chat",
            json={
                "session_id": first["session_id"],
                "language": "en",
                "message": "Still relegion or region",
            },
        ).json()

    assert first["response_type"] == "follow_up"
    assert second["response_type"] == "human_handoff"
    assert second["handoff_reason"] == EscalationReason.UNCLEAR_AFTER_CLARIFICATION.value


def test_mixed_religion_and_network_topic_fails_closed_without_provider() -> None:
    provider = NoCallProvider()
    with TestClient(create_app(provider=provider)) as client:
        body = client.post(
            "/api/v1/chat",
            json={
                "language": "en",
                "message": "Explain religion and also discuss my mobile internet",
            },
        ).json()

    assert body["response_type"] == "refusal"
    assert provider.calls == 0
