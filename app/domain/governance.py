"""Strict Demo 3 source and content-governance models."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from pathlib import PurePath

from pydantic import Field, field_validator, model_validator

from app.domain.enums import Category, Language
from app.domain.schemas import StrictModel


class SourceClassification(StrEnum):
    """Authority and confidentiality classes for supplied sources."""

    OFFICIAL_LEGAL = "official_legal"
    OFFICIAL_OPERATIONAL = "official_operational"
    DEPARTMENT_CANDIDATE = "department_candidate"
    CONFIDENTIAL_CASE = "confidential_case"


class ApprovalStatus(StrEnum):
    """Human content-review states; approval never implies activation."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    WITHDRAWN = "withdrawn"


class ActivationStatus(StrEnum):
    """Independent runtime availability states."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class RecordType(StrEnum):
    """Curated knowledge record types permitted by Demo 3 governance."""

    FAQ = "faq"
    LEGAL_SUMMARY = "legal_summary"
    OPERATIONAL_GUIDANCE = "operational_guidance"


class AnswerMode(StrEnum):
    """Permitted response construction modes."""

    DETERMINISTIC = "deterministic"
    GROUNDED_SUMMARY = "grounded_summary"


class RiskLevel(StrEnum):
    """Reviewable answer-risk levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceManifestEntry(StrictModel):
    """Expected identity and digest for one local source file."""

    source_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$")
    filename: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: SourceClassification

    @field_validator("filename")
    @classmethod
    def require_plain_filename(cls, value: str) -> str:
        """Keep manifests relative and prevent them from selecting arbitrary files."""
        if PurePath(value).name != value or "/" in value or "\\" in value or value in {".", ".."}:
            raise ValueError("filename must be a single relative path component")
        return value


class SourceManifest(StrictModel):
    """Versioned local inventory without extracted source content."""

    manifest_version: int = Field(default=1, ge=1)
    entries: list[SourceManifestEntry]

    @model_validator(mode="after")
    def require_unique_entries(self) -> SourceManifest:
        """Prevent aliases that could make audit results ambiguous."""
        source_ids = [entry.source_id for entry in self.entries]
        filenames = [entry.filename for entry in self.entries]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source IDs must be unique")
        if len(filenames) != len(set(filenames)):
            raise ValueError("source filenames must be unique")
        return self


class KnowledgeSource(StrictModel):
    """Governed source state used before any record can become answerable."""

    source_id: str
    classification: SourceClassification
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    activation_status: ActivationStatus = ActivationStatus.INACTIVE
    content_owner_department: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    source_checked_at: datetime | None = None
    review_due_at: datetime | None = None
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    time_sensitive: bool = False
    quarantined: bool = True
    conflict_ids: list[str] = Field(default_factory=list)


class LegalBasis(StrictModel):
    """Server-owned citation metadata for a curated legal summary."""

    source_id: str
    article_or_clause: str = Field(min_length=1, max_length=200)


class GovernedKnowledgeRecord(StrictModel):
    """Candidate record with approval and activation kept deliberately separate."""

    record_id: str
    record_type: RecordType
    language: Language
    category: Category
    subcategory: str
    question: str
    answer: str
    answer_mode: AnswerMode
    risk_level: RiskLevel
    source_id: str
    source_title: str
    source_url: str | None = None
    legal_basis: list[LegalBasis] = Field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    activation_status: ActivationStatus = ActivationStatus.INACTIVE
    content_owner_department: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    review_due_at: datetime | None = None
    source_checked_at: datetime | None = None
    version: int = Field(default=1, ge=1)
    supersedes: str | None = None
    synthetic: bool = False
    time_sensitive: bool = False
    quarantined: bool = True
    conflict_ids: list[str] = Field(default_factory=list)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_temporal_order(self) -> GovernedKnowledgeRecord:
        """Reject internally contradictory validity and review windows."""
        timestamps = (
            self.approved_at,
            self.valid_from,
            self.valid_until,
            self.review_due_at,
            self.source_checked_at,
        )
        if any(value is not None and value.tzinfo is None for value in timestamps):
            raise ValueError("governance timestamps must include a timezone")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("valid_until must be later than valid_from")
        return self


def governed_content_hash(*, question: str, answer: str) -> str:
    """Hash the exact answerable fields using a stable representation."""
    payload = json.dumps(
        {"answer": answer, "question": question},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
