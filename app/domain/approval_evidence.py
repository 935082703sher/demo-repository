"""Strict approval evidence that never grants runtime activation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from app.domain.enums import Language
from app.domain.governance import ActivationStatus, ApprovalStatus
from app.domain.schemas import StrictModel


class ApprovalTargetType(StrEnum):
    """Individually versioned artifacts that may receive a scoped decision."""

    RECORD = "record"
    REQUIREMENTS_PROFILE = "requirements_profile"
    WORDING = "wording"


class ApprovalEvidence(StrictModel):
    """Named, version-bound decision; blanket or cross-language decisions are invalid."""

    approval_reference: str = Field(min_length=3, max_length=200)
    target_type: ApprovalTargetType
    target_id: str = Field(min_length=3, max_length=200)
    target_version: str = Field(min_length=1, max_length=100)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    language: Language
    approver_name: str = Field(min_length=3, max_length=200)
    approver_role: str = Field(min_length=3, max_length=200)
    approval_date: date
    effective_date: date
    review_or_expiry_date: date
    source_document_reference: str = Field(min_length=3, max_length=300)
    conflict_resolution_reference: str | None = Field(default=None, min_length=3, max_length=300)
    legal_review_reference: str | None = Field(default=None, min_length=3, max_length=300)
    approval_status: Literal[ApprovalStatus.APPROVED] = ApprovalStatus.APPROVED
    activation_status: Literal[ActivationStatus.INACTIVE] = ActivationStatus.INACTIVE
    runtime_eligible: Literal[False] = False

    @model_validator(mode="after")
    def reject_blanket_or_inconsistent_decisions(self) -> ApprovalEvidence:
        """Keep approval atomic, current, and separate from activation."""
        normalized_target = self.target_id.strip().casefold().replace("-", "_")
        if normalized_target in {"all", "approve_all", "all_records", "*"}:
            raise ValueError("blanket approval is prohibited")
        if self.effective_date < self.approval_date:
            raise ValueError("effective date cannot precede approval date")
        if self.review_or_expiry_date <= self.effective_date:
            raise ValueError("review or expiry date must follow effective date")
        if (
            self.target_type is ApprovalTargetType.REQUIREMENTS_PROFILE
            and self.legal_review_reference is None
        ):
            raise ValueError("requirements-profile approval requires legal review reference")
        return self


class ApprovalValidationResult(StrictModel):
    """Evaluation outcome which deliberately cannot activate content."""

    valid: bool
    approval_status: ApprovalStatus
    activation_status: Literal[ActivationStatus.INACTIVE] = ActivationStatus.INACTIVE
    runtime_eligible: Literal[False] = False
    reason_code: str


class ApprovalIntakeResult(StrictModel):
    """Sanitized intake result that never echoes submitted evidence values."""

    accepted: bool
    approval_status: ApprovalStatus
    activation_status: Literal[ActivationStatus.INACTIVE] = ActivationStatus.INACTIVE
    runtime_eligible: Literal[False] = False
    missing_fields: list[str]
    reason_code: str


_REQUIRED_APPROVAL_FIELDS = frozenset(ApprovalEvidence.model_fields) - {
    "conflict_resolution_reference",
    "legal_review_reference",
    "approval_status",
    "activation_status",
    "runtime_eligible",
}


def assess_approval_metadata(payload: Mapping[str, object]) -> ApprovalIntakeResult:
    """Reject incomplete/unparseable evidence using field names only, never raw values."""
    missing = sorted(field for field in _REQUIRED_APPROVAL_FIELDS if not payload.get(field))
    if missing:
        return ApprovalIntakeResult(
            accepted=False,
            approval_status=ApprovalStatus.PENDING_REVIEW,
            missing_fields=missing,
            reason_code="approval_evidence_incomplete",
        )
    try:
        ApprovalEvidence.model_validate(payload)
    except ValueError:
        return ApprovalIntakeResult(
            accepted=False,
            approval_status=ApprovalStatus.PENDING_REVIEW,
            missing_fields=[],
            reason_code="approval_evidence_invalid",
        )
    return ApprovalIntakeResult(
        accepted=True,
        approval_status=ApprovalStatus.APPROVED,
        missing_fields=[],
        reason_code="approval_metadata_valid_but_inactive",
    )


def validate_approval_evidence(
    evidence: ApprovalEvidence,
    *,
    target_id: str,
    target_version: str,
    content_hash: str,
    language: Language,
    as_of: date,
) -> ApprovalValidationResult:
    """Validate exact identity, version, hash, language, and decision lifetime."""
    mismatch = (
        evidence.target_id != target_id
        or evidence.target_version != target_version
        or evidence.content_hash != content_hash
        or evidence.language is not language
    )
    if mismatch:
        return ApprovalValidationResult(
            valid=False,
            approval_status=ApprovalStatus.PENDING_REVIEW,
            reason_code="approval_binding_mismatch",
        )
    if as_of < evidence.effective_date or as_of >= evidence.review_or_expiry_date:
        return ApprovalValidationResult(
            valid=False,
            approval_status=ApprovalStatus.PENDING_REVIEW,
            reason_code="approval_not_current",
        )
    return ApprovalValidationResult(
        valid=True,
        approval_status=ApprovalStatus.APPROVED,
        reason_code="approval_valid_but_inactive",
    )
