"""Feature-gated bridge from legacy draft APIs to the governed Stage 3 workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from threading import RLock
from uuid import UUID, uuid4

from pydantic import SecretStr, ValidationError

from app.core.errors import ConflictError, NotFoundError, RequestValidationError
from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ComplaintWorkflowDraft,
    ComplaintWorkflowState,
    ConsentBinding,
    HandoffReason,
    HumanHandoff,
    LegalReviewStatus,
    ProfileSourceReference,
    RequirementsProfile,
    SecureFieldType,
    SecureValueReference,
    UrgencyClass,
)
from app.domain.enums import Category, DraftStatus, EscalationReason, Language
from app.domain.governance import ApprovalStatus
from app.domain.schemas import (
    ComplaintDraftReview,
    DraftUpsertRequest,
    SubmitRequest,
    SubmitResponse,
)
from app.services.complaint_drafts import (
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    ComplaintDraftService,
    default_subject_for,
    derive_description,
    not_submitted_message,
    submission_not_configured_message,
)
from app.services.complaint_workflow import ComplaintWorkflowEngine
from app.services.pii import scan_text
from app.services.secure_values import SyntheticSecureValueIssuer


@dataclass(frozen=True, slots=True)
class GovernedMappingContext:
    """Explicit server-owned classifications; omitted values stay unknown."""

    applicant_type: ApplicantType = ApplicantType.UNKNOWN
    appeal_kind: AppealKind = AppealKind.UNKNOWN
    subcategory: ComplaintSubcategory = ComplaintSubcategory.UNKNOWN
    required_secure_fields: tuple[SecureFieldType, ...] = ()
    secure_references: tuple[SecureValueReference, ...] = ()
    human_review_reasons: tuple[HandoffReason, ...] = ()


@dataclass(slots=True)
class _CanonicalAdapterRecord:
    """One canonical record: governed state plus its lossless legacy projection inputs."""

    draft: ComplaintWorkflowDraft
    legacy_fields: dict[str, str]
    mapping: GovernedMappingContext


@dataclass(frozen=True, slots=True)
class _SubmissionEvidence:
    idempotency_digest: str
    consent: ConsentBinding
    response: SubmitResponse


_DEFAULT_PROFILE_APPLICANT = ApplicantType.NATURAL_PERSON
_DEFAULT_PROFILE_APPEAL = AppealKind.COMPLAINT
_DEFAULT_SUBCATEGORY = {
    Category.IMEI: ComplaintSubcategory.ERRORS_SUPPORT,
    Category.MNP: ComplaintSubcategory.TRANSFER_CONDITIONS,
}
_LEGACY_REASON_MAP = {
    EscalationReason.CITIZEN_REQUEST: HandoffReason.MANUAL_REVIEW_REQUESTED,
    EscalationReason.EMERGENCY: HandoffReason.EMERGENCY,
    EscalationReason.THREAT_OR_VIOLENCE: HandoffReason.THREAT_OR_VIOLENCE,
    EscalationReason.SELF_HARM: HandoffReason.SELF_HARM,
    EscalationReason.SENSITIVE_DATA: HandoffReason.SENSITIVE_PERSONAL_DATA,
    EscalationReason.CYBERSECURITY: HandoffReason.SERIOUS_CYBERSECURITY_INCIDENT,
    EscalationReason.LEGAL_INTERPRETATION: HandoffReason.LEGAL_INTERPRETATION_REQUESTED,
    EscalationReason.OFFICIAL_DECISION_DISPUTE: HandoffReason.OFFICIAL_DECISION_DISPUTE,
    EscalationReason.MISCONDUCT_ALLEGATION: HandoffReason.MISCONDUCT_OR_CORRUPTION_ALLEGATION,
    EscalationReason.NO_APPROVED_SOURCE: HandoffReason.APPROVED_INFORMATION_UNAVAILABLE,
    EscalationReason.UNCLEAR_AFTER_CLARIFICATION: HandoffReason.UNCLEAR_REQUEST,
    EscalationReason.PROMPT_INJECTION: HandoffReason.MANUAL_REVIEW_REQUESTED,
    EscalationReason.PROVIDER_UNAVAILABLE: HandoffReason.PROVIDER_FAILURE,
    EscalationReason.OUTPUT_VALIDATION_FAILED: HandoffReason.APPROVED_INFORMATION_UNAVAILABLE,
}


class GovernedComplaintWorkflowAdapter:
    """Preserve legacy contracts while selecting exactly one workflow implementation."""

    def __init__(
        self,
        *,
        legacy: ComplaintDraftService,
        enabled: bool,
        privacy_notice_version: str,
        consent_wording_version: str,
    ) -> None:
        self._legacy = legacy
        self.enabled = enabled
        self._privacy_notice_version = privacy_notice_version
        self._consent_wording_version = consent_wording_version
        self._engine = ComplaintWorkflowEngine()
        self._secure_issuer = SyntheticSecureValueIssuer()
        self._records: dict[UUID, _CanonicalAdapterRecord] = {}
        self._submissions: dict[tuple[UUID, int], _SubmissionEvidence] = {}
        self._handoffs: dict[UUID, HumanHandoff] = {}
        self._lock = RLock()

    def upsert(self, request: DraftUpsertRequest) -> ComplaintDraftReview:
        """Use unchanged Demo 2 storage unless the server-owned flag is enabled."""
        if not self.enabled:
            return self._legacy.upsert(request)
        return self.upsert_governed(request)

    def upsert_governed(
        self,
        request: DraftUpsertRequest,
        *,
        mapping: GovernedMappingContext | None = None,
    ) -> ComplaintDraftReview:
        """Create/edit the sole governed source and return a lossless legacy view."""
        if not self.enabled:
            raise RequestValidationError(
                "governed_workflow_disabled",
                "The governed complaint workflow is disabled",
            )
        self._validate_legacy_fields(request.category, request.fields)
        now = datetime.now(UTC)
        with self._lock:
            if request.draft_id is None:
                if request.expected_version is not None:
                    raise RequestValidationError(
                        "unexpected_version",
                        "expected_version is only valid when updating an existing draft",
                    )
                selected_mapping = mapping or GovernedMappingContext()
                fields = dict(request.fields)
                session_id = request.session_id or uuid4()
                profile = self._profile(request.category, selected_mapping)
                try:
                    draft = self._engine.create_draft(
                        profile=profile,
                        session_id=session_id,
                        language=request.language,
                        applicant_type=selected_mapping.applicant_type,
                        appeal_kind=selected_mapping.appeal_kind,
                        category=request.category,
                        subcategory=selected_mapping.subcategory,
                        subject=fields.get("subject")
                        or default_subject_for(request.language, request.category),
                        issue_description=fields.get("description") or derive_description(fields),
                        occurrence_details=self._occurrence_details(fields),
                        secure_references=list(selected_mapping.secure_references),
                        privacy_notice_version=self._privacy_notice_version,
                        human_review_reasons=list(selected_mapping.human_review_reasons),
                        now=now,
                    )
                except (ValidationError, ValueError) as error:
                    raise self._safe_mapping_error(error) from None
                record = _CanonicalAdapterRecord(draft, fields, selected_mapping)
            else:
                record = self._get_active(request.draft_id)
                if request.expected_version is None:
                    raise RequestValidationError(
                        "expected_version_required",
                        "expected_version is required when updating a draft",
                    )
                if request.expected_version != record.draft.version:
                    raise ConflictError(
                        "stale_draft_version",
                        "The draft changed; load the current version before editing",
                    )
                if request.session_id is not None and request.session_id != record.draft.session_id:
                    raise ConflictError("session_mismatch", "The draft belongs to another session")
                if (
                    request.language is not record.draft.language
                    or request.category is not record.draft.category
                ):
                    raise ConflictError(
                        "draft_identity_change",
                        "Language and category cannot be changed by a draft edit",
                    )
                selected_mapping = mapping or record.mapping
                fields = {**record.legacy_fields, **request.fields}
                profile = self._profile(request.category, selected_mapping)
                try:
                    draft = self._engine.edit_draft(
                        record.draft,
                        profile=profile,
                        applicant_type=selected_mapping.applicant_type,
                        appeal_kind=selected_mapping.appeal_kind,
                        subcategory=selected_mapping.subcategory,
                        subject=fields.get("subject")
                        or default_subject_for(request.language, request.category),
                        issue_description=fields.get("description") or derive_description(fields),
                        occurrence_details=self._occurrence_details(fields),
                        secure_references=list(selected_mapping.secure_references),
                        human_review_reasons=list(selected_mapping.human_review_reasons),
                        now=now,
                    )
                except (ValidationError, ValueError) as error:
                    raise self._safe_mapping_error(error) from None
                record = _CanonicalAdapterRecord(draft, fields, selected_mapping)
            self._records[record.draft.draft_id] = record
            return self._to_legacy_review(record)

    def get(self, draft_id: UUID) -> ComplaintDraftReview:
        if not self.enabled:
            return self._legacy.get(draft_id)
        with self._lock:
            record = self._records.get(draft_id)
            if record is None:
                raise NotFoundError("draft_not_found", "Complaint draft was not found")
            return self._to_legacy_review(record)

    def get_governed(self, draft_id: UUID) -> ComplaintWorkflowDraft:
        """Expose a defensive copy for internal tests and migration tooling only."""
        if not self.enabled:
            raise NotFoundError("draft_not_found", "Complaint draft was not found")
        with self._lock:
            record = self._records.get(draft_id)
            if record is None:
                raise NotFoundError("draft_not_found", "Complaint draft was not found")
            return record.draft.model_copy(deep=True)

    def consent_binding(self, draft_id: UUID, version: int) -> ConsentBinding | None:
        """Return redacted internal consent evidence without its idempotency digest."""
        with self._lock:
            evidence = self._submissions.get((draft_id, version))
            return evidence.consent.model_copy(deep=True) if evidence is not None else None

    def cancel(self, draft_id: UUID) -> ComplaintDraftReview:
        if not self.enabled:
            return self._legacy.cancel(draft_id)
        with self._lock:
            record = self._get_active(draft_id)
            cancelled = self._engine.transition(
                record.draft,
                ComplaintWorkflowState.CANCELLED,
                now=datetime.now(UTC),
            )
            updated = _CanonicalAdapterRecord(cancelled, record.legacy_fields, record.mapping)
            self._records[draft_id] = updated
            return self._to_legacy_review(updated)

    def submit(self, draft_id: UUID, request: SubmitRequest, request_id: UUID) -> SubmitResponse:
        if not self.enabled:
            return self._legacy.submit(draft_id, request, request_id)
        with self._lock:
            record = self._get_active(draft_id)
            draft = record.draft
            if not request.consent:
                raise RequestValidationError(
                    "explicit_consent_required",
                    "Press the dedicated Submit control and send consent=true",
                )
            if request.draft_version != draft.version:
                raise ConflictError(
                    "stale_draft_version",
                    "Consent must be bound to the current draft version",
                )
            if request.privacy_notice_version != self._privacy_notice_version:
                raise ConflictError(
                    "privacy_notice_version_mismatch",
                    "Reload the current privacy notice before submitting",
                )
            if scan_text(request.idempotency_key):
                raise RequestValidationError(
                    "unsafe_idempotency_key",
                    "The idempotency key must not contain personal data",
                )
            key = (draft.draft_id, draft.version)
            digest = hashlib.sha256(request.idempotency_key.encode("utf-8")).hexdigest()
            prior = self._submissions.get(key)
            if prior is not None:
                if prior.idempotency_digest != digest:
                    raise ConflictError(
                        "duplicate_submit",
                        "A Submit event was already recorded for this draft version",
                    )
                return prior.response.model_copy(
                    update={"request_id": request_id, "idempotent_replay": True}
                )
            if draft.workflow_state is not ComplaintWorkflowState.REVIEW_READY:
                raise ConflictError(
                    "incomplete_draft",
                    "The governed draft requires clarification, missing fields, or human review",
                )
            now = datetime.now(UTC)
            awaiting = self._engine.transition(
                draft,
                ComplaintWorkflowState.AWAITING_CONSENT,
                now=now,
            )
            consent = ConsentBinding(
                draft_id=awaiting.draft_id,
                draft_version=awaiting.version,
                draft_hash=awaiting.draft_hash,
                privacy_notice_version=awaiting.privacy_notice_version,
                consent_wording_version=self._consent_wording_version,
                language=awaiting.language,
                consent_given=True,
                recorded_at=now,
            )
            consented = self._engine.record_consent(awaiting, consent)
            blocked = self._engine.block_submission(consented, now=now)
            updated = _CanonicalAdapterRecord(blocked, record.legacy_fields, record.mapping)
            self._records[draft_id] = updated
            response = SubmitResponse(
                request_id=request_id,
                success=False,
                status="official_integration_not_configured",
                officially_registered=False,
                case_number=None,
                message=submission_not_configured_message(draft.language),
                idempotent_replay=False,
            )
            self._submissions[key] = _SubmissionEvidence(digest, consent, response)
            return response

    def issue_synthetic_secure_reference(
        self,
        *,
        field_type: SecureFieldType,
        synthetic_value: SecretStr,
    ) -> SecureValueReference:
        """Use only the non-retaining synthetic issuer; no production provider exists."""
        if not self.enabled:
            raise RequestValidationError(
                "governed_workflow_disabled",
                "The governed complaint workflow is disabled",
            )
        return self._secure_issuer.issue_reference(
            field_type=field_type,
            synthetic_value=synthetic_value,
        )

    def observe_legacy_handoff(
        self,
        session_id: UUID,
        language: Language,
        reason: EscalationReason,
        correlation_id: UUID,
    ) -> None:
        """Record a typed internal projection while preserving the exact legacy reason."""
        governed_reason = _LEGACY_REASON_MAP[reason]
        urgency = (
            UrgencyClass.IMMEDIATE_SAFETY
            if reason
            in {
                EscalationReason.EMERGENCY,
                EscalationReason.THREAT_OR_VIOLENCE,
                EscalationReason.SELF_HARM,
            }
            else UrgencyClass.STANDARD
        )
        handoff = HumanHandoff(
            reason=governed_reason,
            urgency=urgency,
            safe_summary=f"legacy_reason={reason.value}",
            language=language,
            created_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )
        with self._lock:
            self._handoffs[session_id] = handoff

    def last_handoff(self, session_id: UUID) -> HumanHandoff | None:
        with self._lock:
            value = self._handoffs.get(session_id)
            return value.model_copy(deep=True) if value is not None else None

    def _get_active(self, draft_id: UUID) -> _CanonicalAdapterRecord:
        record = self._records.get(draft_id)
        if record is None:
            raise NotFoundError("draft_not_found", "Complaint draft was not found")
        if record.draft.workflow_state is ComplaintWorkflowState.CANCELLED:
            raise ConflictError("draft_cancelled", "The complaint draft has been cancelled")
        return record

    @staticmethod
    def _validate_legacy_fields(category: Category, fields: dict[str, str]) -> None:
        allowed = set(REQUIRED_FIELDS[category]) | OPTIONAL_FIELDS
        unsupported = sorted(set(fields) - allowed)
        if unsupported:
            raise RequestValidationError(
                "unsupported_draft_fields",
                f"Unsupported fields for {category.value}: {', '.join(unsupported)}",
            )

    @staticmethod
    def _occurrence_details(fields: dict[str, str]) -> dict[str, str]:
        return {
            key: value for key, value in fields.items() if key not in {"subject", "description"}
        }

    @staticmethod
    def _safe_mapping_error(error: ValueError) -> RequestValidationError:
        code = (
            "sensitive_draft_data_rejected"
            if isinstance(error, ValidationError) and "sensitive" in str(error).casefold()
            else "governed_mapping_rejected"
        )
        return RequestValidationError(code, "The draft could not be mapped safely")

    @staticmethod
    def _profile(category: Category, mapping: GovernedMappingContext) -> RequirementsProfile:
        applicant = (
            mapping.applicant_type
            if mapping.applicant_type is not ApplicantType.UNKNOWN
            else _DEFAULT_PROFILE_APPLICANT
        )
        appeal = (
            mapping.appeal_kind
            if mapping.appeal_kind is not AppealKind.UNKNOWN
            else _DEFAULT_PROFILE_APPEAL
        )
        subcategory = (
            mapping.subcategory
            if mapping.subcategory is not ComplaintSubcategory.UNKNOWN
            else _DEFAULT_SUBCATEGORY.get(category, ComplaintSubcategory.UNKNOWN)
        )
        profile_key = (
            "-".join((category.value, applicant.value, appeal.value, subcategory.value))
            .upper()
            .replace("_", "-")
        )
        secure_key = (
            hashlib.sha256(
                ",".join(sorted(field.value for field in mapping.required_secure_fields)).encode(
                    "utf-8"
                )
            )
            .hexdigest()[:8]
            .upper()
        )
        profile_key = f"{profile_key}-{secure_key}"
        required = [
            "issue_description" if field == "description" else field
            for field in REQUIRED_FIELDS[category]
        ]
        secure = list(mapping.required_secure_fields)
        return RequirementsProfile(
            profile_id=f"SYNTHETIC-PROFILE-STAGE3B-{profile_key}",
            profile_version=1,
            effective_date=date(2026, 8, 11),
            applicant_type=applicant,
            appeal_kind=appeal,
            category=category,
            subcategory=subcategory,
            required_non_sensitive_fields=required,
            required_secure_fields=secure,
            prohibited_from_ordinary_storage=secure,
            approval_status=ApprovalStatus.PENDING_REVIEW,
            legal_review_status=LegalReviewStatus.PENDING_REVIEW,
            owner_role="Synthetic Stage 3B workflow owner",
            source_references=[
                ProfileSourceReference(
                    source_id="SYNTHETIC-STAGE3B-ADAPTER-001",
                    source_version=1,
                )
            ],
            production_eligible=False,
            provisional=True,
        )

    @staticmethod
    def _to_legacy_review(record: _CanonicalAdapterRecord) -> ComplaintDraftReview:
        draft = record.draft
        missing = [
            "description" if field == "issue_description" else field
            for field in draft.missing_required_fields
        ]
        if draft.applicant_type is ApplicantType.UNKNOWN:
            missing.append("applicant_type")
        if draft.appeal_kind is AppealKind.UNKNOWN:
            missing.append("appeal_kind")
        if draft.subcategory in {ComplaintSubcategory.UNKNOWN, ComplaintSubcategory.UNSUPPORTED}:
            missing.append("subcategory")
        missing = sorted(set(missing))
        return ComplaintDraftReview(
            draft_id=draft.draft_id,
            session_id=draft.session_id,
            version=draft.version,
            draft_hash=draft.draft_hash,
            status=(
                DraftStatus.CANCELLED
                if draft.workflow_state is ComplaintWorkflowState.CANCELLED
                else DraftStatus.ACTIVE
            ),
            language=draft.language,
            category=draft.category,
            subject=draft.subject or default_subject_for(draft.language, draft.category),
            description=draft.issue_description or derive_description(record.legacy_fields),
            fields=dict(record.legacy_fields),
            fields_missing=missing,
            personal_data_to_submit=[
                reference.field_type.value for reference in draft.secure_references
            ],
            complete=draft.workflow_state is ComplaintWorkflowState.REVIEW_READY,
            not_submitted_notice=not_submitted_message(draft.language),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
