"""Deterministic local Stage 3C complaint-orchestration facade."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from uuid import UUID, uuid4

from pydantic import SecretStr

from app.core.errors import ConflictError
from app.domain.complaint_orchestration import (
    GovernedComplaintInput,
    GovernedComplaintReview,
    GovernedHandoffResult,
    GovernedOrchestrationResult,
    MaskedSecureReference,
    OrchestrationOutcome,
)
from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ComplaintWorkflowDraft,
    ComplaintWorkflowState,
    HandoffReason,
    HumanHandoff,
    MessageKey,
    OperatorQueueStatus,
    SecureFieldType,
    SecureValueReference,
    UrgencyClass,
)
from app.domain.enums import Category, EscalationReason, Language
from app.domain.schemas import DraftUpsertRequest, SubmitRequest, SubmitResponse
from app.i18n.follow_up_questions import follow_up_question
from app.services.classifier import RequestClassifier, normalize_text
from app.services.complaint_workflow_adapter import (
    GovernedComplaintWorkflowAdapter,
    GovernedMappingContext,
)
from app.services.guardrails import Guardrails
from app.services.pii import scan_text
from app.services.scope import ScopeService, ScopeStatus


class GovernedComplaintOrchestrator:
    """Connect internal workflow decisions without an LLM or official-system client."""

    def __init__(
        self,
        *,
        adapter: GovernedComplaintWorkflowAdapter,
        privacy_notice_version: str,
        consent_wording_version: str,
        classifier: RequestClassifier | None = None,
        guardrails: Guardrails | None = None,
        scope: ScopeService | None = None,
    ) -> None:
        if not adapter.enabled:
            raise ValueError("governed_orchestrator_requires_enabled_adapter")
        self._adapter = adapter
        self._privacy_notice_version = privacy_notice_version
        self._consent_wording_version = consent_wording_version
        self._classifier = classifier or RequestClassifier()
        self._guardrails = guardrails or Guardrails()
        self._scope = scope or ScopeService()
        self._reviewed: set[tuple[UUID, int, str]] = set()
        self._clarification_counts: dict[UUID, int] = {}
        self._lock = RLock()

    def issue_synthetic_secure_reference(
        self,
        *,
        field_type: SecureFieldType,
        synthetic_value: SecretStr,
    ) -> SecureValueReference:
        """Expose only the non-retaining local synthetic secure-value boundary."""
        return self._adapter.issue_synthetic_secure_reference(
            field_type=field_type,
            synthetic_value=synthetic_value,
        )

    def draft_snapshot(self, draft_id: UUID) -> ComplaintWorkflowDraft:
        """Return an internal defensive copy for local verification tools."""
        return self._adapter.get_governed(draft_id)

    def handle(self, request: GovernedComplaintInput) -> GovernedOrchestrationResult:
        """Apply language, safety, scope, classification, and draft rules in order."""
        session_id = request.session_id or uuid4()
        now = datetime.now(UTC)
        if request.language is None:
            return self._result(
                outcome=OrchestrationOutcome.LANGUAGE_SELECTION,
                session_id=session_id,
                language=None,
                now=now,
            )

        safety = self._guardrails.check_input(request.message)
        if not safety.allowed:
            legacy_reason = safety.handoff_reason or EscalationReason.OUTPUT_VALIDATION_FAILED
            return self._legacy_handoff(
                session_id=session_id,
                language=request.language,
                reason=legacy_reason,
                now=now,
            )
        if scan_text(request.message):
            return self._handoff(
                session_id=session_id,
                language=request.language,
                reason=HandoffReason.SENSITIVE_PERSONAL_DATA,
                now=now,
            )

        protected_reason = self._protected_request_reason(request.message)
        if protected_reason is not None:
            return self._handoff(
                session_id=session_id,
                language=request.language,
                reason=protected_reason,
                now=now,
            )
        direct_reason = self._direct_handoff_reason(request.message)
        if direct_reason is not None:
            return self._handoff(
                session_id=session_id,
                language=request.language,
                reason=direct_reason,
                now=now,
            )

        scope = self._scope.classify(request.message)
        if scope.status is ScopeStatus.OUT_OF_SCOPE:
            return self._result(
                outcome=OrchestrationOutcome.SCOPE_REFUSAL,
                session_id=session_id,
                language=request.language,
                now=now,
            )
        if (
            scope.status is ScopeStatus.AMBIGUOUS
            and request.category is None
            and request.draft_id is None
        ):
            if self._increment_clarification(session_id) > 1:
                return self._handoff(
                    session_id=session_id,
                    language=request.language,
                    reason=HandoffReason.UNCLEAR_REQUEST,
                    now=now,
                )
            key, question = follow_up_question(request.language, "subcategory")
            return self._result(
                outcome=OrchestrationOutcome.CLARIFICATION,
                session_id=session_id,
                language=request.language,
                message_key=MessageKey.CLARIFICATION_REQUIRED,
                follow_up_key=key,
                follow_up_question=question,
                now=now,
            )

        applicant_type = self._applicant_type(request)
        appeal_kind = self._appeal_kind(request)
        category = request.category or self._classifier.classify(request.message).category
        subcategory = self._subcategory(request, category)
        reasons = list(request.human_review_reasons)
        if subcategory is ComplaintSubcategory.UNSUPPORTED:
            reasons.append(HandoffReason.UNSUPPORTED_CATEGORY)

        review = self._adapter.upsert_governed(
            DraftUpsertRequest(
                session_id=session_id,
                draft_id=request.draft_id,
                expected_version=request.expected_version,
                language=request.language,
                category=category,
                fields=request.fields,
            ),
            mapping=GovernedMappingContext(
                applicant_type=applicant_type,
                appeal_kind=appeal_kind,
                subcategory=subcategory,
                required_secure_fields=tuple(request.required_secure_fields),
                secure_references=tuple(request.secure_references),
                human_review_reasons=tuple(reasons),
            ),
        )
        draft = self._adapter.get_governed(review.draft_id)
        governed_review = self._review(draft)
        if draft.workflow_state is ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED:
            return self._handoff(
                session_id=draft.session_id,
                language=draft.language,
                reason=draft.human_review_reasons[0],
                review=governed_review,
                now=now,
            )
        if draft.workflow_state is ComplaintWorkflowState.REVIEW_READY:
            return self._result(
                outcome=OrchestrationOutcome.REVIEW_READY,
                session_id=draft.session_id,
                language=draft.language,
                workflow_state=draft.workflow_state,
                message_key=MessageKey.DRAFT_READY,
                review=governed_review,
                now=now,
            )

        next_field = governed_review.missing_fields[0]
        key, question = follow_up_question(draft.language, next_field)
        outcome = (
            OrchestrationOutcome.CLARIFICATION
            if draft.workflow_state is ComplaintWorkflowState.CLARIFICATION_REQUIRED
            else OrchestrationOutcome.COLLECTING
        )
        if outcome is OrchestrationOutcome.CLARIFICATION:
            if self._increment_clarification(draft.session_id) > 1:
                return self._handoff(
                    session_id=draft.session_id,
                    language=draft.language,
                    reason=HandoffReason.UNCLEAR_REQUEST,
                    review=governed_review,
                    now=now,
                )
        else:
            self._reset_clarification(draft.session_id)
        return self._result(
            outcome=outcome,
            session_id=draft.session_id,
            language=draft.language,
            workflow_state=draft.workflow_state,
            message_key=(
                MessageKey.CLARIFICATION_REQUIRED
                if outcome is OrchestrationOutcome.CLARIFICATION
                else MessageKey.MISSING_FIELDS
            ),
            follow_up_key=key,
            follow_up_question=question,
            review=governed_review,
            now=now,
        )

    def acknowledge_review(self, draft_id: UUID, version: int, canonical_hash: str) -> None:
        """Acknowledge the exact current local review before consent is accepted."""
        self._adapter.acknowledge_review(draft_id, version, canonical_hash)
        with self._lock:
            self._reviewed.add((draft_id, version, canonical_hash))

    def consent(
        self,
        *,
        draft_id: UUID,
        version: int,
        canonical_hash: str,
        idempotency_key: str,
        request_id: UUID | None = None,
    ) -> tuple[GovernedOrchestrationResult, SubmitResponse]:
        """Bind local consent and end at submission_blocked, never official processing."""
        with self._lock:
            if (draft_id, version, canonical_hash) not in self._reviewed:
                raise ConflictError(
                    "draft_review_required",
                    "Review the current draft version before recording consent",
                )
        current = self._adapter.get_governed(draft_id)
        if current.version != version or current.draft_hash != canonical_hash:
            raise ConflictError(
                "stale_draft_review",
                "Consent must reference the current reviewed version and hash",
            )
        response = self._adapter.submit(
            draft_id,
            SubmitRequest(
                consent=True,
                draft_version=version,
                privacy_notice_version=self._privacy_notice_version,
                idempotency_key=idempotency_key,
            ),
            request_id or uuid4(),
        )
        updated = self._adapter.get_governed(draft_id)
        return (
            self._result(
                outcome=OrchestrationOutcome.SUBMISSION_BLOCKED,
                session_id=updated.session_id,
                language=updated.language,
                workflow_state=updated.workflow_state,
                message_key=MessageKey.SUBMISSION_UNAVAILABLE,
                review=self._review(updated),
                now=datetime.now(UTC),
            ),
            response,
        )

    def cancel(self, draft_id: UUID) -> GovernedOrchestrationResult:
        """Cancel local workflow state without official side effects."""
        self._adapter.cancel(draft_id)
        draft = self._adapter.get_governed(draft_id)
        return self._result(
            outcome=OrchestrationOutcome.CANCELLED,
            session_id=draft.session_id,
            language=draft.language,
            workflow_state=draft.workflow_state,
            message_key=MessageKey.CANCELLED,
            review=self._review(draft),
            now=datetime.now(UTC),
        )

    def _review(self, draft: ComplaintWorkflowDraft) -> GovernedComplaintReview:
        legacy = self._adapter.get(draft.draft_id)
        missing = list(legacy.fields_missing)
        return GovernedComplaintReview(
            applicant_type=draft.applicant_type,
            appeal_kind=draft.appeal_kind,
            category=draft.category,
            subcategory=draft.subcategory,
            subject=draft.subject or legacy.subject,
            structured_issue_description=draft.issue_description or legacy.description,
            occurrence_details=dict(draft.occurrence_details),
            secure_reference_indicators=[
                MaskedSecureReference(field_type=reference.field_type)
                for reference in draft.secure_references
            ],
            missing_fields=missing,
            human_review_status=draft.human_review_status,
            draft_id=draft.draft_id,
            synthetic_session_id=draft.session_id,
            version=draft.version,
            canonical_hash=draft.draft_hash,
            language=draft.language,
            privacy_notice_version=draft.privacy_notice_version,
            consent_wording_version=self._consent_wording_version,
            not_officially_registered_notice=legacy.not_submitted_notice,
        )

    def _increment_clarification(self, session_id: UUID) -> int:
        with self._lock:
            count = self._clarification_counts.get(session_id, 0) + 1
            self._clarification_counts[session_id] = count
            return count

    def _reset_clarification(self, session_id: UUID) -> None:
        with self._lock:
            self._clarification_counts.pop(session_id, None)

    def _legacy_handoff(
        self,
        *,
        session_id: UUID,
        language: Language,
        reason: EscalationReason,
        now: datetime,
    ) -> GovernedOrchestrationResult:
        self._adapter.observe_legacy_handoff(session_id, language, reason, uuid4())
        handoff = self._adapter.last_handoff(session_id)
        if handoff is None:
            raise RuntimeError("typed_handoff_mapping_failed")
        return self._handoff_result(handoff, session_id=session_id, language=language, now=now)

    def _handoff(
        self,
        *,
        session_id: UUID,
        language: Language,
        reason: HandoffReason,
        now: datetime,
        review: GovernedComplaintReview | None = None,
    ) -> GovernedOrchestrationResult:
        urgency = (
            UrgencyClass.IMMEDIATE_SAFETY
            if reason
            in {HandoffReason.EMERGENCY, HandoffReason.THREAT_OR_VIOLENCE, HandoffReason.SELF_HARM}
            else UrgencyClass.STANDARD
        )
        handoff = HumanHandoff(
            reason=reason,
            urgency=urgency,
            safe_summary=f"synthetic_handoff_reason={reason.value}",
            language=language,
            created_at=now,
            correlation_id=uuid4(),
            operator_queue_status=OperatorQueueStatus.NOT_CONFIGURED,
        )
        return self._handoff_result(
            handoff,
            session_id=session_id,
            language=language,
            now=now,
            review=review,
        )

    def _handoff_result(
        self,
        handoff: HumanHandoff,
        *,
        session_id: UUID,
        language: Language,
        now: datetime,
        review: GovernedComplaintReview | None = None,
    ) -> GovernedOrchestrationResult:
        return self._result(
            outcome=OrchestrationOutcome.HUMAN_HANDOFF,
            session_id=session_id,
            language=language,
            workflow_state=(
                ComplaintWorkflowState.HUMAN_REVIEW_REQUIRED if review is not None else None
            ),
            message_key=MessageKey.HUMAN_REVIEW_REQUIRED,
            review=review,
            handoff=GovernedHandoffResult(
                handoff=handoff,
                preserved_reason=handoff.reason,
            ),
            now=now,
        )

    @staticmethod
    def _applicant_type(request: GovernedComplaintInput) -> ApplicantType:
        if request.applicant_type is not ApplicantType.UNKNOWN:
            return request.applicant_type
        text = normalize_text(request.message)
        signals = (
            (
                ApplicantType.AUTHORIZED_REPRESENTATIVE,
                ("authorized representative", "vakil", "представител"),
            ),
            (ApplicantType.LEGAL_ENTITY, ("legal entity", "yuridik shaxs", "юридическое лицо")),
            (
                ApplicantType.NATURAL_PERSON,
                ("natural person", "individual", "jismoniy shaxs", "физическое лицо"),
            ),
        )
        return next(
            (kind for kind, phrases in signals if any(phrase in text for phrase in phrases)),
            ApplicantType.UNKNOWN,
        )

    @staticmethod
    def _appeal_kind(request: GovernedComplaintInput) -> AppealKind:
        if request.appeal_kind is not AppealKind.UNKNOWN:
            return request.appeal_kind
        text = normalize_text(request.message)
        signals = (
            (AppealKind.PROPOSAL, ("proposal", "suggestion", "taklif", "предложение")),
            (
                AppealKind.COMPLAINT,
                ("complaint", "problem", "issue", "shikoyat", "muammo", "жалоб", "проблем"),
            ),
            (
                AppealKind.APPLICATION,
                (
                    "application",
                    "information request",
                    "ariza",
                    "ma'lumot",
                    "заявление",
                    "информационный запрос",
                ),
            ),
        )
        return next(
            (kind for kind, phrases in signals if any(phrase in text for phrase in phrases)),
            AppealKind.UNKNOWN,
        )

    @staticmethod
    def _subcategory(
        request: GovernedComplaintInput,
        category: Category,
    ) -> ComplaintSubcategory:
        if request.subcategory is not ComplaintSubcategory.UNKNOWN:
            return request.subcategory
        text = normalize_text(request.message)
        if "unsupported" in text:
            return ComplaintSubcategory.UNSUPPORTED
        if category is Category.IMEI:
            if "status" in text or "статус" in text:
                return ComplaintSubcategory.STATUS_CHECK
            return ComplaintSubcategory.ERRORS_SUPPORT
        if category is Category.MNP:
            if "rejected" in text or "отказ" in text:
                return ComplaintSubcategory.REJECTED_TRANSFER
            return ComplaintSubcategory.TRANSFER_CONDITIONS
        return {
            Category.NUMBER_CODES: ComplaintSubcategory.NUMBER_CODE_INFORMATION,
            Category.NETWORK_QUALITY: ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            Category.WEBSITE_ISSUE: ComplaintSubcategory.WEBSITE_FUNCTIONAL_ERROR,
            Category.OTHER: ComplaintSubcategory.OTHER_RTMCMATTER,
        }[category]

    @staticmethod
    def _protected_request_reason(message: str) -> HandoffReason | None:
        text = normalize_text(message)
        if any(
            term in text
            for term in (
                "legal deadline",
                "guaranteed deadline",
                "response deadline",
                "qonuniy muddat",
                "срок ответа",
            )
        ):
            return HandoffReason.LEGAL_INTERPRETATION_REQUESTED
        return None

    @staticmethod
    def _direct_handoff_reason(message: str) -> HandoffReason | None:
        text = normalize_text(message)
        signals = (
            (
                HandoffReason.MINOR_OR_VULNERABLE_PERSON,
                ("minor person", "vulnerable person", "voyaga yetmagan", "несовершеннолет"),
            ),
            (
                HandoffReason.IDENTITY_OR_AUTHORITY_UNCLEAR,
                ("authority is unclear", "identity is unclear"),
            ),
            (HandoffReason.SOURCE_CONFLICT, ("unresolved source conflict",)),
            (HandoffReason.APPROVED_INFORMATION_UNAVAILABLE, ("approved information unavailable",)),
            (
                HandoffReason.MANUAL_REVIEW_REQUESTED,
                ("human review", "human operator", "inson ko'rigi", "проверка человеком"),
            ),
        )
        return next(
            (reason for reason, phrases in signals if any(phrase in text for phrase in phrases)),
            None,
        )

    @staticmethod
    def _result(
        *,
        outcome: OrchestrationOutcome,
        session_id: UUID,
        language: Language | None,
        now: datetime,
        workflow_state: ComplaintWorkflowState | None = None,
        message_key: MessageKey | None = None,
        follow_up_key: str | None = None,
        follow_up_question: str | None = None,
        review: GovernedComplaintReview | None = None,
        handoff: GovernedHandoffResult | None = None,
    ) -> GovernedOrchestrationResult:
        return GovernedOrchestrationResult(
            outcome=outcome,
            session_id=session_id,
            language=language,
            workflow_state=workflow_state,
            message_key=message_key,
            follow_up_key=follow_up_key,
            follow_up_question=follow_up_question,
            review=review,
            handoff=handoff,
            created_at=now,
        )
