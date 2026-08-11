"""Strict Stage 2 models for review-only multilingual knowledge candidates."""

from __future__ import annotations

import hmac
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from app.domain.enums import Category, Language
from app.domain.governance import (
    ActivationStatus,
    AnswerMode,
    ApprovalStatus,
    RiskLevel,
    governed_content_hash,
)
from app.domain.schemas import StrictModel


class VerificationOutcome(StrEnum):
    """How one public source relates to a candidate claim."""

    SUPPORTS = "supports"
    PARTIALLY_SUPPORTS = "partially_supports"
    DOES_NOT_ADDRESS = "does_not_address"


class VerificationStatus(StrEnum):
    """Aggregate public-source verification state for a review candidate."""

    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    PENDING = "pending"


class ConflictStatus(StrEnum):
    """Candidates in this package must be free of unresolved conflicts."""

    CLEAR = "clear"


class SensitivityClassification(StrEnum):
    """Only privacy-reviewed public-candidate content is allowed in Git."""

    PUBLIC_CANDIDATE = "public_candidate"


class TranslationMethod(StrEnum):
    """Reviewable provenance for an unapproved translation draft."""

    MACHINE_ASSISTED_ENGINEERING_DRAFT = "machine_assisted_engineering_draft"


class VerificationEvidence(StrictModel):
    """Content-free source metadata and a concise claim-level comparison."""

    url: str
    page_title: str = Field(min_length=1, max_length=300)
    retrieved_at: datetime
    section: str = Field(min_length=1, max_length=300)
    outcome: VerificationOutcome
    note: str = Field(min_length=1, max_length=800)

    @field_validator("url")
    @classmethod
    def require_https_url(cls, value: str) -> str:
        """Forbid local paths, credentials, fragments, and non-HTTPS citations."""
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("verification URL must be a public HTTPS URL")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def require_retrieval_timezone(cls, value: datetime) -> datetime:
        """Make freshness evidence comparable across environments."""
        if value.tzinfo is None:
            raise ValueError("retrieved_at must include a timezone")
        return value


class TranslationProvenance(StrictModel):
    """Link a draft translation to the exact Uzbek candidate version."""

    source_language: Language
    source_record_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,95}$")
    source_version: int = Field(ge=1)
    source_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    method: TranslationMethod

    @model_validator(mode="after")
    def require_uzbek_source(self) -> TranslationProvenance:
        """Russian and English drafts may derive only from the Uzbek record."""
        if self.source_language is not Language.UZ:
            raise ValueError("translation source language must be Uzbek")
        return self


class KnowledgeCandidate(StrictModel):
    """A privacy-reviewed record that remains unavailable until human activation."""

    record_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,95}$")
    language: Language
    category: Category
    subcategory: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    question: str = Field(min_length=3, max_length=1000)
    question_variants: list[str] = Field(min_length=1, max_length=8)
    answer: str = Field(min_length=3, max_length=6000)
    answer_mode: AnswerMode = AnswerMode.DETERMINISTIC
    risk_level: RiskLevel
    source_document_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_paragraphs: list[int] = Field(min_length=1, max_length=64)
    official_sources: list[VerificationEvidence] = Field(min_length=1, max_length=8)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_owner_role: str = Field(min_length=3, max_length=200)
    content_owner_name: None = None
    legal_reviewer_role: str | None = Field(default=None, max_length=200)
    legal_reviewer_name: None = None
    translation_reviewer_role: str | None = Field(default=None, max_length=200)
    translation_reviewer_name: None = None
    sensitivity: SensitivityClassification = SensitivityClassification.PUBLIC_CANDIDATE
    time_sensitive: bool
    valid_from: None = None
    valid_until: None = None
    review_due_at: datetime
    last_verified_at: datetime
    verification_status: VerificationStatus
    conflict_status: ConflictStatus = ConflictStatus.CLEAR
    approval_status: ApprovalStatus = ApprovalStatus.PENDING_REVIEW
    activation_status: ActivationStatus = ActivationStatus.INACTIVE
    runtime_eligible: bool = False
    quarantined: bool = True
    synthetic: bool = False
    approved_by: None = None
    approved_at: None = None
    translation_approved: bool = False
    legal_summary_approved: bool = False
    translation_provenance: TranslationProvenance | None = None
    review_decision: None = None
    reviewer_name: None = None
    reviewer_position: None = None
    decision_timestamp: None = None
    reviewer_comments: None = None
    version: int = Field(default=1, ge=1)

    @field_validator("question_variants")
    @classmethod
    def require_unique_question_variants(cls, values: list[str]) -> list[str]:
        """Reject blank or duplicate matching text before human review."""
        normalized = [" ".join(value.split()).casefold() for value in values]
        if any(not value for value in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("question variants must be non-empty and unique")
        return values

    @field_validator("source_paragraphs")
    @classmethod
    def require_ordered_source_paragraphs(cls, values: list[int]) -> list[int]:
        """Keep references deterministic and prevent hidden invalid ranges."""
        if any(value < 1 for value in values) or values != sorted(set(values)):
            raise ValueError("source paragraphs must be positive, sorted, and unique")
        return values

    @model_validator(mode="after")
    def enforce_review_only_state(self) -> KnowledgeCandidate:
        """Make accidental approval or activation invalid at the data boundary."""
        if self.approval_status is not ApprovalStatus.PENDING_REVIEW:
            raise ValueError("Stage 2 candidates must be pending review")
        if self.activation_status is not ActivationStatus.INACTIVE:
            raise ValueError("Stage 2 candidates must be inactive")
        if self.runtime_eligible or not self.quarantined or self.synthetic:
            raise ValueError("Stage 2 candidates must be real, quarantined, and runtime-ineligible")
        if self.translation_approved or self.legal_summary_approved:
            raise ValueError("Stage 2 review flags must remain false")
        if self.last_verified_at.tzinfo is None or self.review_due_at.tzinfo is None:
            raise ValueError("candidate timestamps must include a timezone")
        if self.review_due_at <= self.last_verified_at:
            raise ValueError("review_due_at must be later than last_verified_at")
        expected_hash = governed_content_hash(question=self.question, answer=self.answer)
        if not hmac.compare_digest(expected_hash, self.content_sha256):
            raise ValueError("candidate content hash mismatch")
        if self.verification_status is VerificationStatus.VERIFIED and not any(
            evidence.outcome is VerificationOutcome.SUPPORTS for evidence in self.official_sources
        ):
            raise ValueError("verified candidate requires supporting evidence")
        if self.verification_status is VerificationStatus.PENDING and not any(
            evidence.outcome is VerificationOutcome.DOES_NOT_ADDRESS
            for evidence in self.official_sources
        ):
            raise ValueError("pending candidate requires explicit non-coverage evidence")
        if self.language is Language.UZ:
            if (
                self.translation_provenance is not None
                or self.translation_reviewer_role is not None
            ):
                raise ValueError("Uzbek source candidates cannot claim translation provenance")
        elif self.translation_provenance is None or not self.translation_reviewer_role:
            raise ValueError("translation drafts require source provenance and reviewer role")
        return self


class CandidatePackage(StrictModel):
    """One language-level package with deterministic uniqueness guarantees."""

    package_version: int = Field(default=1, ge=1)
    stage: str = Field(pattern=r"^demo3_stage2$")
    language: Language
    source_document_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,63}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    records: list[KnowledgeCandidate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_package_consistency(self) -> CandidatePackage:
        """Reject duplicate IDs, duplicate questions, and cross-source aliases."""
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        ids = [record.record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate record IDs must be unique")
        question_keys = [
            (record.category, record.subcategory, " ".join(record.question.split()).casefold())
            for record in self.records
        ]
        if len(question_keys) != len(set(question_keys)):
            raise ValueError("duplicate candidate questions are not allowed")
        for record in self.records:
            if (
                record.language is not self.language
                or record.source_document_id != self.source_document_id
                or not hmac.compare_digest(record.source_sha256, self.source_sha256)
            ):
                raise ValueError("candidate package metadata mismatch")
        return self
