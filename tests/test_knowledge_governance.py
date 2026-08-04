"""Strict source and record lifecycle activation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import Category, Language
from app.domain.governance import (
    ActivationStatus,
    AnswerMode,
    ApprovalStatus,
    GovernedKnowledgeRecord,
    KnowledgeSource,
    RecordType,
    RiskLevel,
    SourceClassification,
    governed_content_hash,
)
from app.services.knowledge_governance import (
    activation_transition_allowed,
    approval_transition_allowed,
    record_activation_failures,
    record_is_retrievable,
)

NOW = datetime(2026, 8, 3, tzinfo=UTC)


def active_source(**updates: object) -> KnowledgeSource:
    values: dict[str, object] = {
        "source_id": "DEPT-TEST-001",
        "classification": SourceClassification.DEPARTMENT_CANDIDATE,
        "approval_status": ApprovalStatus.APPROVED,
        "activation_status": ActivationStatus.ACTIVE,
        "content_owner_department": "Synthetic Content Team",
        "approved_by": "synthetic-reviewer",
        "approved_at": NOW - timedelta(days=1),
        "source_checked_at": NOW - timedelta(days=1),
        "review_due_at": NOW + timedelta(days=30),
        "expected_sha256": "1" * 64,
        "observed_sha256": "1" * 64,
        "time_sensitive": False,
        "quarantined": False,
        "conflict_ids": [],
    }
    values.update(updates)
    return KnowledgeSource.model_validate(values)


def active_record(**updates: object) -> GovernedKnowledgeRecord:
    question = "Synthetic approved citizen question"
    answer = "Synthetic approved answer for governance testing only."
    values: dict[str, object] = {
        "record_id": "FAQ-TEST-UZ-001",
        "record_type": RecordType.FAQ,
        "language": Language.UZ,
        "category": Category.IMEI,
        "subcategory": "registration_general",
        "question": question,
        "answer": answer,
        "answer_mode": AnswerMode.DETERMINISTIC,
        "risk_level": RiskLevel.LOW,
        "source_id": "DEPT-TEST-001",
        "source_title": "Synthetic candidate source",
        "source_url": None,
        "legal_basis": [],
        "approval_status": ApprovalStatus.APPROVED,
        "activation_status": ActivationStatus.ACTIVE,
        "content_owner_department": "Synthetic Content Team",
        "approved_by": "synthetic-reviewer",
        "approved_at": NOW - timedelta(days=1),
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=30),
        "review_due_at": NOW + timedelta(days=20),
        "source_checked_at": NOW - timedelta(days=1),
        "version": 1,
        "supersedes": None,
        "synthetic": False,
        "time_sensitive": False,
        "quarantined": False,
        "conflict_ids": [],
        "content_sha256": governed_content_hash(question=question, answer=answer),
    }
    values.update(updates)
    return GovernedKnowledgeRecord.model_validate(values)


def test_only_fully_approved_active_current_record_is_retrievable() -> None:
    assert record_is_retrievable(
        active_record(),
        active_source(),
        language=Language.UZ,
        now=NOW,
    )


@pytest.mark.parametrize(
    ("updates", "failure"),
    [
        ({"approval_status": ApprovalStatus.PENDING_REVIEW}, "record_not_approved"),
        ({"activation_status": ActivationStatus.INACTIVE}, "record_not_active"),
        ({"valid_until": NOW}, "record_expired"),
        ({"review_due_at": None}, "record_review_due_missing"),
        ({"quarantined": True}, "record_quarantined"),
        ({"conflict_ids": ["CONFLICT-TEST-001"]}, "record_conflict"),
        ({"content_sha256": "0" * 64}, "record_hash_mismatch"),
    ],
)
def test_record_activation_fails_closed(updates: dict[str, object], failure: str) -> None:
    failures = record_activation_failures(
        active_record(**updates),
        active_source(),
        language=Language.UZ,
        now=NOW,
    )

    assert failure in failures


def test_source_hash_mismatch_and_conflict_block_all_records() -> None:
    source = active_source(observed_sha256="2" * 64, conflict_ids=["CONFLICT-TEST-001"])
    failures = record_activation_failures(
        active_record(),
        source,
        language=Language.UZ,
        now=NOW,
    )

    assert "source_hash_mismatch" in failures
    assert "source_conflict" in failures


def test_wrong_language_and_unapproved_translation_are_not_retrievable() -> None:
    pending_translation = active_record(
        record_id="FAQ-TEST-RU-001",
        language=Language.RU,
        approval_status=ApprovalStatus.PENDING_REVIEW,
        activation_status=ActivationStatus.INACTIVE,
    )

    assert not record_is_retrievable(
        active_record(), active_source(), language=Language.EN, now=NOW
    )
    assert not record_is_retrievable(
        pending_translation, active_source(), language=Language.RU, now=NOW
    )


def test_unapproved_legal_summary_remains_inactive() -> None:
    record = active_record(
        record_type=RecordType.LEGAL_SUMMARY,
        approval_status=ApprovalStatus.PENDING_REVIEW,
        activation_status=ActivationStatus.INACTIVE,
    )

    assert not record_is_retrievable(record, active_source(), language=Language.UZ, now=NOW)


def test_time_sensitive_record_requires_expiry_and_review_metadata() -> None:
    record = active_record(time_sensitive=True, valid_until=None, review_due_at=None)
    failures = record_activation_failures(
        record,
        active_source(),
        language=Language.UZ,
        now=NOW,
    )

    assert "time_sensitive_valid_until_missing" in failures
    assert "record_review_due_missing" in failures


def test_lifecycle_transitions_are_explicit_and_terminal() -> None:
    assert approval_transition_allowed(ApprovalStatus.DRAFT, ApprovalStatus.PENDING_REVIEW)
    assert approval_transition_allowed(ApprovalStatus.PENDING_REVIEW, ApprovalStatus.APPROVED)
    assert not approval_transition_allowed(ApprovalStatus.DRAFT, ApprovalStatus.APPROVED)
    assert activation_transition_allowed(ActivationStatus.INACTIVE, ActivationStatus.ACTIVE)
    assert activation_transition_allowed(ActivationStatus.ACTIVE, ActivationStatus.EXPIRED)
    assert not activation_transition_allowed(ActivationStatus.WITHDRAWN, ActivationStatus.ACTIVE)
