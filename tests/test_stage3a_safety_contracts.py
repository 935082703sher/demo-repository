"""Stage 3A secure-field, handoff, anti-invention, and message tests."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid1, uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.domain.complaint_workflow import (
    HandoffReason,
    HumanHandoff,
    MessageKey,
    OperatorQueueStatus,
    ProtectedClaim,
    SecureFieldType,
    SecureStorageProvider,
    SecureValueReference,
    UrgencyClass,
)
from app.domain.enums import Language
from app.i18n.workflow_messages import SYNTHETIC_WORKFLOW_MESSAGES, synthetic_workflow_message
from app.services.complaint_authority_policy import AuthorityContext, evaluate_protected_claim
from app.services.secure_values import SyntheticSecureValueIssuer

NOW = datetime(2026, 8, 11, 12, tzinfo=UTC)


def test_secure_reference_is_opaque_masked_and_closed() -> None:
    reference = SecureValueReference(
        reference_id=uuid4(),
        field_type=SecureFieldType.IDENTITY_DOCUMENT,
    )
    serialized = reference.model_dump(mode="json")

    assert serialized["masked_display"] == "***"
    assert serialized["storage_provider"] == SecureStorageProvider.NOT_CONFIGURED.value
    assert serialized["verified"] is False
    assert set(serialized) == {
        "reference_id",
        "field_type",
        "masked_display",
        "storage_provider",
        "verified",
    }
    with pytest.raises(ValidationError):
        SecureValueReference.model_validate({**serialized, "raw_value": "forbidden"})


def test_secure_reference_rejects_sequential_identifier() -> None:
    with pytest.raises(ValidationError, match="UUIDv4"):
        SecureValueReference(
            reference_id=uuid1(),
            field_type=SecureFieldType.IDENTITY_DOCUMENT,
        )


def test_synthetic_secure_issuer_rejects_likely_real_pii_and_retains_no_value() -> None:
    issuer = SyntheticSecureValueIssuer()
    raw = "+998 90 123 45 67"
    with pytest.raises(ValueError, match="synthetic_secure_value_required"):
        issuer.issue_reference(
            field_type=SecureFieldType.PRIVATE_TELEPHONE,
            synthetic_value=SecretStr(raw),
        )

    synthetic = "SYNTHETIC_TEST_VALUE_ALPHA"
    reference = issuer.issue_reference(
        field_type=SecureFieldType.IDENTITY_DOCUMENT,
        synthetic_value=SecretStr(synthetic),
    )
    representation = repr(reference)
    serialized = json.dumps(reference.model_dump(mode="json"))
    assert synthetic not in representation + serialized
    assert raw not in representation + serialized


def test_secure_reference_logging_does_not_expose_input(caplog: pytest.LogCaptureFixture) -> None:
    synthetic = "SYNTHETIC_TEST_VALUE_LOGGING"
    reference = SyntheticSecureValueIssuer().issue_reference(
        field_type=SecureFieldType.SIGNATURE,
        synthetic_value=SecretStr(synthetic),
    )
    with caplog.at_level(logging.INFO):
        logging.getLogger("stage3a-test").info("secure_reference=%r", reference)

    assert synthetic not in caplog.text
    assert "***" in caplog.text


def test_secret_string_representation_is_redacted() -> None:
    raw = "SYNTHETIC_TEST_VALUE_NEVER_LOG"
    protected = SecretStr(raw)

    assert raw not in repr(protected)
    assert raw not in str(protected)


def test_handoff_is_non_sensitive_and_queue_remains_unconfigured() -> None:
    handoff = HumanHandoff(
        reason=HandoffReason.MANUAL_REVIEW_REQUESTED,
        urgency=UrgencyClass.STANDARD,
        safe_summary="Synthetic matter requires manual review",
        missing_information_keys=["issue_description"],
        language=Language.EN,
        created_at=NOW,
        correlation_id=UUID("20000000-0000-4000-8000-000000000001"),
    )

    assert handoff.operator_queue_status is OperatorQueueStatus.NOT_CONFIGURED
    assert "operator" not in handoff.model_dump(mode="json")
    with pytest.raises(ValidationError, match="sensitive data"):
        handoff.model_copy(
            update={"safe_summary": "email: synthetic.person@example.test"}
        ).__class__.model_validate(
            {
                **handoff.model_dump(mode="python"),
                "safe_summary": "email: synthetic.person@example.test",
            }
        )


def test_all_required_handoff_reasons_are_closed_and_available() -> None:
    expected = {
        "emergency",
        "threat_or_violence",
        "self_harm",
        "sensitive_personal_data",
        "legal_interpretation_requested",
        "official_decision_dispute",
        "misconduct_or_corruption_allegation",
        "serious_cybersecurity_incident",
        "identity_or_authority_unclear",
        "minor_or_vulnerable_person",
        "unclear_request",
        "unsupported_category",
        "source_conflict",
        "approved_information_unavailable",
        "provider_failure",
        "manual_review_requested",
    }
    assert {reason.value for reason in HandoffReason} == expected


@pytest.mark.parametrize("claim", list(ProtectedClaim))
def test_protected_claims_fail_closed_without_server_owned_authority(
    claim: ProtectedClaim,
) -> None:
    decision = evaluate_protected_claim(claim, context=AuthorityContext())

    assert decision.allowed is False
    assert decision.handoff_reason is HandoffReason.APPROVED_INFORMATION_UNAVAILABLE
    assert decision.message_key is MessageKey.UNSUPPORTED_AUTHORITY_REQUEST


def test_approved_source_cannot_invent_official_case_or_status() -> None:
    context = AuthorityContext(approved_active_source_ids=("SYNTHETIC-ACTIVE-SOURCE",))

    assert evaluate_protected_claim(
        ProtectedClaim.LEGAL_INTERPRETATION,
        context=context,
    ).allowed
    assert not evaluate_protected_claim(ProtectedClaim.CASE_NUMBER, context=context).allowed
    assert not evaluate_protected_claim(ProtectedClaim.COMPLAINT_STATUS, context=context).allowed


def test_message_keys_are_complete_same_language_and_explicitly_synthetic() -> None:
    expected_keys: set[MessageKey] = set(MessageKey)
    assert set(SYNTHETIC_WORKFLOW_MESSAGES) == set(Language)
    for language in Language:
        assert set(SYNTHETIC_WORKFLOW_MESSAGES[language]) == expected_keys
        for key in expected_keys:
            message = synthetic_workflow_message(language, key)
            assert message.startswith(("[SINTETIK]", "[СИНТЕТИКА]", "[SYNTHETIC]"))


def test_foreign_acronym_does_not_change_selected_message_language() -> None:
    assert "СИНТЕТИКА" in synthetic_workflow_message(Language.RU, MessageKey.DRAFT_READY)
    assert "SYNTHETIC" in synthetic_workflow_message(Language.EN, MessageKey.DRAFT_READY)
