"""Closed Stage 3A contracts for a governed, non-official complaint workflow."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.enums import Category, Language
from app.domain.governance import ApprovalStatus
from app.domain.schemas import ShortText, StrictModel
from app.services.pii import is_sensitive_field_name, scan_text


class ApplicantType(StrEnum):
    """Provisional applicant classifications; unknown requires clarification."""

    NATURAL_PERSON = "natural_person"
    LEGAL_ENTITY = "legal_entity"
    AUTHORIZED_REPRESENTATIVE = "authorized_representative"
    UNKNOWN = "unknown"


class AppealKind(StrEnum):
    """Versioned technical identifiers, not approved citizen-facing legal labels."""

    APPLICATION = "application"
    PROPOSAL = "proposal"
    COMPLAINT = "complaint"
    UNKNOWN = "unknown"


class ComplaintSubcategory(StrEnum):
    """Existing controlled Stage 2 subcategories plus explicit unresolved states."""

    DEVICE_IMPORT = "device_import"
    DUAL_SIM_MULTIPLE_IMEI = "dual_sim_multiple_imei"
    ERRORS_SUPPORT = "errors_support"
    FOREIGN_CITIZENS = "foreign_citizens"
    REGISTRATION_ELIGIBILITY = "registration_eligibility"
    REGISTRATION_METHODS = "registration_methods"
    REQUIRED_DOCUMENTS = "required_documents"
    STATUS_CHECK = "status_check"
    TARIFFS = "tariffs"
    APPLICATION_PROCEDURE = "application_procedure"
    DEBT_BALANCE = "debt_balance"
    ELIGIBILITY = "eligibility"
    NUMBER_OWNERSHIP = "number_ownership"
    OPERATOR_SELECTION = "operator_selection"
    REJECTED_TRANSFER = "rejected_transfer"
    SERVICE_FEE = "service_fee"
    TRANSFER_CONDITIONS = "transfer_conditions"
    TRANSFER_TIMING = "transfer_timing"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


IMEI_SUBCATEGORIES = frozenset(
    {
        ComplaintSubcategory.DEVICE_IMPORT,
        ComplaintSubcategory.DUAL_SIM_MULTIPLE_IMEI,
        ComplaintSubcategory.ERRORS_SUPPORT,
        ComplaintSubcategory.FOREIGN_CITIZENS,
        ComplaintSubcategory.REGISTRATION_ELIGIBILITY,
        ComplaintSubcategory.REGISTRATION_METHODS,
        ComplaintSubcategory.REQUIRED_DOCUMENTS,
        ComplaintSubcategory.STATUS_CHECK,
        ComplaintSubcategory.TARIFFS,
    }
)
MNP_SUBCATEGORIES = frozenset(
    {
        ComplaintSubcategory.APPLICATION_PROCEDURE,
        ComplaintSubcategory.DEBT_BALANCE,
        ComplaintSubcategory.ELIGIBILITY,
        ComplaintSubcategory.NUMBER_OWNERSHIP,
        ComplaintSubcategory.OPERATOR_SELECTION,
        ComplaintSubcategory.REJECTED_TRANSFER,
        ComplaintSubcategory.REQUIRED_DOCUMENTS,
        ComplaintSubcategory.SERVICE_FEE,
        ComplaintSubcategory.STATUS_CHECK,
        ComplaintSubcategory.TRANSFER_CONDITIONS,
        ComplaintSubcategory.TRANSFER_TIMING,
    }
)


class SecureFieldType(StrEnum):
    """Sensitive values that ordinary draft and chat storage may never contain."""

    IDENTITY_DOCUMENT = "identity_document"
    PINFL_JSHSHIR = "pinfl_jshshir"
    FULL_IMEI = "full_imei"
    PRIVATE_TELEPHONE = "private_telephone"
    RESIDENTIAL_ADDRESS = "residential_address"
    PERSONAL_EMAIL = "personal_email"
    SIGNATURE = "signature"
    IDENTITY_DOCUMENT_IMAGE = "identity_document_image"
    CONFIDENTIAL_ATTACHMENT = "confidential_attachment"
    LEGAL_ENTITY_REGISTRATION_ID = "legal_entity_registration_id"
    REPRESENTATIVE_AUTHORIZATION = "representative_authorization"


class SecureStorageProvider(StrEnum):
    """Stage 3A has no production secure-storage provider."""

    NOT_CONFIGURED = "not_configured"
    SYNTHETIC_MEMORY = "synthetic_memory"


class LegalReviewStatus(StrEnum):
    """Independent review state for provisional requirements profiles."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class ComplaintWorkflowState(StrEnum):
    """Internal states with no implication of official government processing."""

    COLLECTING = "collecting"
    CLARIFICATION_REQUIRED = "clarification_required"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    REVIEW_READY = "review_ready"
    AWAITING_CONSENT = "awaiting_consent"
    CONSENT_RECORDED = "consent_recorded"
    SUBMISSION_BLOCKED = "submission_blocked"
    CANCELLED = "cancelled"


class ConsentState(StrEnum):
    """Local consent state; it never represents submission authority."""

    NOT_RECORDED = "not_recorded"
    RECORDED = "recorded"
    INVALIDATED = "invalidated"


class HumanReviewStatus(StrEnum):
    """Whether deterministic rules require a human decision."""

    NOT_REQUIRED = "not_required"
    REQUIRED = "required"


class HandoffReason(StrEnum):
    """Stable Stage 3A reasons for stopping automated handling."""

    EMERGENCY = "emergency"
    THREAT_OR_VIOLENCE = "threat_or_violence"
    SELF_HARM = "self_harm"
    SENSITIVE_PERSONAL_DATA = "sensitive_personal_data"
    LEGAL_INTERPRETATION_REQUESTED = "legal_interpretation_requested"
    OFFICIAL_DECISION_DISPUTE = "official_decision_dispute"
    MISCONDUCT_OR_CORRUPTION_ALLEGATION = "misconduct_or_corruption_allegation"
    SERIOUS_CYBERSECURITY_INCIDENT = "serious_cybersecurity_incident"
    IDENTITY_OR_AUTHORITY_UNCLEAR = "identity_or_authority_unclear"
    MINOR_OR_VULNERABLE_PERSON = "minor_or_vulnerable_person"
    UNCLEAR_REQUEST = "unclear_request"
    UNSUPPORTED_CATEGORY = "unsupported_category"
    SOURCE_CONFLICT = "source_conflict"
    APPROVED_INFORMATION_UNAVAILABLE = "approved_information_unavailable"
    PROVIDER_FAILURE = "provider_failure"
    MANUAL_REVIEW_REQUESTED = "manual_review_requested"


class UrgencyClass(StrEnum):
    """Non-SLA urgency classification for safe handling."""

    STANDARD = "standard"
    PRIORITY_REVIEW = "priority_review"
    IMMEDIATE_SAFETY = "immediate_safety"


class OperatorQueueStatus(StrEnum):
    """No human operator queue is configured in Stage 3A."""

    NOT_CONFIGURED = "not_configured"


class MessageKey(StrEnum):
    """Stable keys for later legally approved citizen-facing wording."""

    CLARIFICATION_REQUIRED = "workflow.clarification_required"
    MISSING_FIELDS = "workflow.missing_fields"
    HUMAN_REVIEW_REQUIRED = "workflow.human_review_required"
    SENSITIVE_DATA_WARNING = "workflow.sensitive_data_warning"
    DRAFT_READY = "workflow.draft_ready"
    CONSENT_REQUIRED = "workflow.consent_required"
    CONSENT_INVALIDATED = "workflow.consent_invalidated"
    SUBMISSION_UNAVAILABLE = "workflow.submission_unavailable"
    CANCELLED = "workflow.cancelled"
    UNSUPPORTED_AUTHORITY_REQUEST = "workflow.unsupported_authority_request"


class ProtectedClaim(StrEnum):
    """Claims requiring approved evidence or a separately authorized integration."""

    LEGAL_INTERPRETATION = "legal_interpretation"
    LEGAL_CONCLUSION = "legal_conclusion"
    ELIGIBILITY_DECISION = "eligibility_decision"
    OFFICIAL_DEADLINE = "official_deadline"
    GUARANTEED_PROCESSING_PERIOD = "guaranteed_processing_period"
    TARIFF_INTERPRETATION = "tariff_interpretation"
    RESPONSIBLE_DEPARTMENT_ASSIGNMENT = "responsible_department_assignment"
    COMPLAINT_ACCEPTANCE = "complaint_acceptance"
    CASE_NUMBER = "case_number"
    COMPLAINT_STATUS = "complaint_status"
    FINAL_DECISION = "final_decision"
    COMPENSATION_ENTITLEMENT = "compensation_entitlement"
    ENFORCEMENT_ACTION = "enforcement_action"


class ProfileSourceReference(StrictModel):
    """Provisional source pointer that cannot imply legal approval."""

    source_id: str = Field(pattern=r"^SYNTHETIC-[A-Z0-9-]{3,80}$")
    source_version: int = Field(ge=1)
    synthetic: Literal[True] = True
    approved: Literal[False] = False


class ConditionalRequirement(StrictModel):
    """Declarative conditional fields without embedding legal conclusions in code."""

    when_field: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    equals_value: str = Field(min_length=1, max_length=100)
    required_non_sensitive_fields: list[str] = Field(default_factory=list)
    required_secure_fields: list[SecureFieldType] = Field(default_factory=list)

    @field_validator("required_non_sensitive_fields")
    @classmethod
    def validate_non_sensitive_keys(cls, values: list[str]) -> list[str]:
        """Reject duplicate, malformed, or sensitive ordinary-storage fields."""
        _validate_ordinary_field_keys(values)
        return values

    @model_validator(mode="after")
    def validate_condition(self) -> ConditionalRequirement:
        """Keep conditions non-sensitive, deterministic, and meaningful."""
        _validate_ordinary_field_keys([self.when_field])
        if scan_text(self.equals_value):
            raise ValueError("conditional requirements cannot contain likely sensitive data")
        if len(self.required_secure_fields) != len(set(self.required_secure_fields)):
            raise ValueError("conditional secure fields must be unique")
        if not self.required_non_sensitive_fields and not self.required_secure_fields:
            raise ValueError("conditional requirement must add at least one field")
        return self


class RequirementsProfile(StrictModel):
    """Versioned, provisional field-requirement profile for engineering review."""

    profile_id: str = Field(pattern=r"^SYNTHETIC-PROFILE-[A-Z0-9-]{3,80}$")
    profile_version: int = Field(ge=1)
    effective_date: date
    applicant_type: ApplicantType
    appeal_kind: AppealKind
    category: Category
    subcategory: ComplaintSubcategory
    required_non_sensitive_fields: list[str]
    required_secure_fields: list[SecureFieldType]
    conditional_requirements: list[ConditionalRequirement] = Field(default_factory=list)
    prohibited_from_ordinary_storage: list[SecureFieldType]
    human_review_triggers: list[HandoffReason] = Field(default_factory=list)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING_REVIEW
    legal_review_status: LegalReviewStatus = LegalReviewStatus.PENDING_REVIEW
    owner_role: str = Field(min_length=3, max_length=200)
    owner_name: None = None
    source_references: list[ProfileSourceReference] = Field(min_length=1)
    production_eligible: Literal[False] = False
    provisional: Literal[True] = True

    @field_validator("required_non_sensitive_fields")
    @classmethod
    def validate_required_fields(cls, values: list[str]) -> list[str]:
        """Keep ordinary requirements deterministic and free of sensitive keys."""
        _validate_ordinary_field_keys(values)
        return values

    @model_validator(mode="after")
    def enforce_provisional_state(self) -> RequirementsProfile:
        """No Stage 3A profile can masquerade as approved legal requirements."""
        if self.approval_status is not ApprovalStatus.PENDING_REVIEW:
            raise ValueError("Stage 3A profiles must remain pending review")
        if self.legal_review_status is not LegalReviewStatus.PENDING_REVIEW:
            raise ValueError("Stage 3A profiles must remain pending legal review")
        if self.applicant_type is ApplicantType.UNKNOWN or self.appeal_kind is AppealKind.UNKNOWN:
            raise ValueError("requirements profiles require an explicit provisional classification")
        if not subcategory_is_compatible(self.category, self.subcategory):
            raise ValueError("requirements profile category and subcategory are incompatible")
        if len(self.required_secure_fields) != len(set(self.required_secure_fields)):
            raise ValueError("required secure fields must be unique")
        conditional_secure = {
            field_type
            for condition in self.conditional_requirements
            for field_type in condition.required_secure_fields
        }
        prohibited = set(self.prohibited_from_ordinary_storage)
        if len(prohibited) != len(self.prohibited_from_ordinary_storage):
            raise ValueError("prohibited secure fields must be unique")
        if (set(self.required_secure_fields) | conditional_secure) - prohibited:
            raise ValueError("required secure fields must be prohibited from ordinary storage")
        source_ids = [source.source_id for source in self.source_references]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("profile source references must be unique")
        if len(self.human_review_triggers) != len(set(self.human_review_triggers)):
            raise ValueError("human review triggers must be unique")
        return self


class SecureValueReference(StrictModel):
    """Opaque metadata-only handle; the protected value is never represented here."""

    reference_id: UUID
    field_type: SecureFieldType
    masked_display: Literal["***"] = "***"
    storage_provider: SecureStorageProvider = SecureStorageProvider.NOT_CONFIGURED
    verified: Literal[False] = False

    @field_validator("reference_id")
    @classmethod
    def require_random_uuid(cls, value: UUID) -> UUID:
        """Require UUIDv4 so identifiers are opaque and non-sequential."""
        if value.version != 4:
            raise ValueError("secure reference identifiers must be random UUIDv4 values")
        return value


class HumanHandoff(StrictModel):
    """Safe internal handoff intent with no claim that an operator received it."""

    reason: HandoffReason
    urgency: UrgencyClass
    safe_summary: str = Field(min_length=1, max_length=500)
    missing_information_keys: list[str] = Field(default_factory=list)
    language: Language
    created_at: datetime
    correlation_id: UUID
    operator_queue_status: OperatorQueueStatus = OperatorQueueStatus.NOT_CONFIGURED

    @model_validator(mode="after")
    def reject_sensitive_summary(self) -> HumanHandoff:
        """Ensure summaries and keys cannot carry citizen identifiers."""
        if self.created_at.tzinfo is None:
            raise ValueError("handoff timestamp must include a timezone")
        if scan_text(self.safe_summary):
            raise ValueError("handoff summary contains likely sensitive data")
        _validate_identifier_keys(self.missing_information_keys)
        return self


class ConsentBinding(StrictModel):
    """Explicit local consent bound to one exact non-official draft version."""

    draft_id: UUID
    draft_version: int = Field(ge=1)
    draft_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_notice_version: str = Field(min_length=1, max_length=100)
    consent_wording_version: str = Field(min_length=1, max_length=100)
    language: Language
    consent_given: Literal[True]
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Consent timestamps must be unambiguous."""
        if value.tzinfo is None:
            raise ValueError("consent timestamp must include a timezone")
        return value


class ComplaintWorkflowDraft(StrictModel):
    """Minimum PII-screened content plus opaque secure references."""

    draft_id: UUID
    session_id: UUID
    language: Language
    applicant_type: ApplicantType
    appeal_kind: AppealKind
    category: Category
    subcategory: ComplaintSubcategory
    subject: str | None = Field(default=None, min_length=1, max_length=300)
    issue_description: str | None = Field(default=None, min_length=1, max_length=4000)
    occurrence_details: dict[str, ShortText] = Field(default_factory=dict)
    secure_references: list[SecureValueReference] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    human_review_status: HumanReviewStatus = HumanReviewStatus.NOT_REQUIRED
    human_review_reasons: list[HandoffReason] = Field(default_factory=list)
    workflow_state: ComplaintWorkflowState
    version: int = Field(ge=1)
    draft_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    updated_at: datetime
    requirements_profile_id: str = Field(pattern=r"^SYNTHETIC-PROFILE-[A-Z0-9-]{3,80}$")
    requirements_profile_version: int = Field(ge=1)
    privacy_notice_version: str = Field(min_length=1, max_length=100)
    consent_state: ConsentState = ConsentState.NOT_RECORDED

    @field_validator("subject", "issue_description")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Reject whitespace-only content and normalize insignificant whitespace."""
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("draft text must not be blank")
        return normalized

    @model_validator(mode="after")
    def enforce_safe_and_canonical_draft(self) -> ComplaintWorkflowDraft:
        """Reject PII, contradictory workflow state, and non-canonical hashes."""
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("draft timestamps must include a timezone")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if not subcategory_is_compatible(self.category, self.subcategory):
            raise ValueError("draft category and subcategory are incompatible")
        _validate_ordinary_field_keys(list(self.occurrence_details))
        _validate_identifier_keys(self.missing_required_fields)
        ordinary_text = [
            value
            for value in (self.subject, self.issue_description, *self.occurrence_details.values())
            if value is not None
        ]
        if any(scan_text(value) for value in ordinary_text):
            raise ValueError("ordinary complaint draft contains likely sensitive data")
        reference_ids = [reference.reference_id for reference in self.secure_references]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("secure reference identifiers must be unique")
        if self.human_review_status is HumanReviewStatus.REQUIRED and not self.human_review_reasons:
            raise ValueError("required human review must include a typed reason")
        if self.human_review_status is HumanReviewStatus.NOT_REQUIRED and self.human_review_reasons:
            raise ValueError("human review reasons require human_review_status=required")
        advanced_states = {
            ComplaintWorkflowState.REVIEW_READY,
            ComplaintWorkflowState.AWAITING_CONSENT,
            ComplaintWorkflowState.CONSENT_RECORDED,
            ComplaintWorkflowState.SUBMISSION_BLOCKED,
        }
        if self.workflow_state in advanced_states and (
            self.missing_required_fields
            or self.applicant_type is ApplicantType.UNKNOWN
            or self.appeal_kind is AppealKind.UNKNOWN
            or self.subcategory
            in {
                ComplaintSubcategory.UNKNOWN,
                ComplaintSubcategory.UNSUPPORTED,
            }
            or self.human_review_status is HumanReviewStatus.REQUIRED
        ):
            raise ValueError("advanced draft state requires complete deterministic classification")
        if (
            self.workflow_state
            in {
                ComplaintWorkflowState.CONSENT_RECORDED,
                ComplaintWorkflowState.SUBMISSION_BLOCKED,
            }
            and self.consent_state is not ConsentState.RECORDED
        ):
            raise ValueError("post-consent workflow state requires current recorded consent")
        expected_hash = canonical_draft_hash(self)
        if not hmac.compare_digest(expected_hash, self.draft_hash):
            raise ValueError("complaint draft hash mismatch")
        return self


def subcategory_is_compatible(category: Category, subcategory: ComplaintSubcategory) -> bool:
    """Keep controlled subcategories tied to their service category."""
    if subcategory in {ComplaintSubcategory.UNKNOWN, ComplaintSubcategory.UNSUPPORTED}:
        return True
    if category is Category.IMEI:
        return subcategory in IMEI_SUBCATEGORIES
    if category is Category.MNP:
        return subcategory in MNP_SUBCATEGORIES
    return False


def canonical_draft_hash(draft_or_values: ComplaintWorkflowDraft | dict[str, object]) -> str:
    """Hash semantic draft content deterministically across ordering and restarts."""
    if isinstance(draft_or_values, ComplaintWorkflowDraft):
        values = draft_or_values.model_dump(mode="json")
    else:
        values = draft_or_values
    hash_fields = {
        key: values[key]
        for key in (
            "language",
            "applicant_type",
            "appeal_kind",
            "category",
            "subcategory",
            "subject",
            "issue_description",
            "occurrence_details",
            "secure_references",
            "missing_required_fields",
            "human_review_status",
            "human_review_reasons",
            "version",
            "requirements_profile_id",
            "requirements_profile_version",
            "privacy_notice_version",
        )
    }
    canonical = json.dumps(
        _normalize_for_hash(hash_fields),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _normalize_for_hash(value: object) -> object:
    if isinstance(value, StrictModel):
        return _normalize_for_hash(value.model_dump(mode="json"))
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_for_hash(nested) for key, nested in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_normalize_for_hash(nested) for nested in value]
    return value


def _validate_identifier_keys(values: list[str]) -> None:
    normalized = [value.strip().casefold() for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError("field keys must be unique")
    for value in normalized:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", value):
            raise ValueError("field keys must be snake-case identifiers")


def _validate_ordinary_field_keys(values: list[str]) -> None:
    _validate_identifier_keys(values)
    secure_names = {field_type.value for field_type in SecureFieldType}
    if any(is_sensitive_field_name(value) or value in secure_names for value in values):
        raise ValueError("ordinary field keys must not identify protected data")
