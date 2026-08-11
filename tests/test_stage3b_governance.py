"""Stage 3B approval evidence and inactive-link registry tests."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.approval_evidence import (
    ApprovalEvidence,
    ApprovalTargetType,
    validate_approval_evidence,
)
from app.domain.approved_links import LinkLanguage
from app.domain.enums import Language
from app.domain.governance import ActivationStatus, ApprovalStatus
from app.services.approved_links import stage3b_link_registry


def evidence(**updates: object) -> ApprovalEvidence:
    values: dict[str, object] = {
        "approval_reference": "SYNTHETIC-DECISION-001",
        "target_type": ApprovalTargetType.RECORD,
        "target_id": "SYNTHETIC-RECORD-001",
        "target_version": "1",
        "content_hash": "a" * 64,
        "language": Language.UZ,
        "approver_name": "Synthetic Approver",
        "approver_role": "Synthetic Content Owner",
        "approval_date": date(2026, 8, 10),
        "effective_date": date(2026, 8, 11),
        "review_or_expiry_date": date(2026, 9, 11),
        "source_document_reference": "SYNTHETIC-DOC-001",
    }
    values.update(updates)
    return ApprovalEvidence.model_validate(values)


def test_exact_approval_can_be_valid_but_never_activates_runtime() -> None:
    result = validate_approval_evidence(
        evidence(),
        target_id="SYNTHETIC-RECORD-001",
        target_version="1",
        content_hash="a" * 64,
        language=Language.UZ,
        as_of=date(2026, 8, 11),
    )

    assert result.valid
    assert result.approval_status is ApprovalStatus.APPROVED
    assert result.activation_status is ActivationStatus.INACTIVE
    assert result.runtime_eligible is False


def test_language_hash_version_or_expiry_mismatch_remains_pending() -> None:
    for target_version, content_hash, language in (
        ("1", "a" * 64, Language.RU),
        ("1", "b" * 64, Language.UZ),
        ("2", "a" * 64, Language.UZ),
    ):
        result = validate_approval_evidence(
            evidence(),
            target_id="SYNTHETIC-RECORD-001",
            target_version=target_version,
            content_hash=content_hash,
            language=language,
            as_of=date(2026, 8, 11),
        )
        assert result.valid is False
        assert result.approval_status is ApprovalStatus.PENDING_REVIEW

    expired = validate_approval_evidence(
        evidence(),
        target_id="SYNTHETIC-RECORD-001",
        target_version="1",
        content_hash="a" * 64,
        language=Language.UZ,
        as_of=date(2026, 9, 11),
    )
    assert expired.approval_status is ApprovalStatus.PENDING_REVIEW


def test_blanket_and_incomplete_approval_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError, match="blanket approval"):
        evidence(target_id="approve_all")
    values = evidence().model_dump(mode="python")
    del values["approver_name"]
    with pytest.raises(ValidationError):
        ApprovalEvidence.model_validate(values)


def test_all_reviewed_links_are_pending_inactive_and_unresolvable() -> None:
    registry = stage3b_link_registry()
    entries = registry.entries()

    assert len(entries) == 13
    assert len({entry.link_id for entry in entries}) == 13
    assert all(entry.approval_status is ApprovalStatus.PENDING_REVIEW for entry in entries)
    assert all(
        not entry.active and not entry.runtime_eligible and entry.test_only for entry in entries
    )
    assert all(registry.resolve_runtime(entry.link_id, entry.language) is None for entry in entries)


def test_registry_prevents_url_invention_and_cross_language_fallback() -> None:
    registry = stage3b_link_registry()

    assert registry.resolve_runtime("invented_url", LinkLanguage.EN) is None
    assert registry.resolve_runtime("mnp_ru", LinkLanguage.EN) is None
