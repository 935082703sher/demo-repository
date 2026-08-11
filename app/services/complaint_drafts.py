"""In-memory complaint drafts, consent records, and safe Demo 1 submission."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID, uuid4

from app.core.errors import ConflictError, NotFoundError, RequestValidationError
from app.domain.enums import Category, DraftStatus, Language
from app.domain.schemas import (
    ComplaintDraftReview,
    ConsentRecord,
    DraftUpsertRequest,
    SubmitRequest,
    SubmitResponse,
)

REQUIRED_FIELDS: dict[Category, tuple[str, ...]] = {
    Category.IMEI: ("request_kind", "action_attempted", "observed_result", "event_time"),
    Category.MNP: (
        "request_kind",
        "current_stage",
        "operator",
        "submitted_at",
        "observed_error",
    ),
    Category.NUMBER_CODES: ("code_type", "country_or_region", "request_kind"),
    Category.NETWORK_QUALITY: (
        "operator",
        "service_type",
        "region",
        "district",
        "approximate_location",
        "event_time",
        "frequency",
        "duration",
        "impact",
    ),
    Category.WEBSITE_ISSUE: (
        "page_url",
        "action_attempted",
        "error_message",
        "event_time",
        "device_type",
        "browser_type",
    ),
    Category.OTHER: ("description", "desired_outcome"),
}

OPTIONAL_FIELDS = {
    "subject",
    "description",
    "requested_action",
    "reference_number",
}

_NOT_SUBMITTED = {
    Language.UZ: (
        "Bu faqat murojaat loyihasi. “Yuborish” tugmasini bosmaguningizcha "
        "murojaat rasmiy ro'yxatdan o'tkazilmaydi."
    ),
    Language.RU: (
        "Это только проект обращения. Оно не будет официально зарегистрировано, "
        "пока Вы не нажмёте «Отправить»."
    ),
    Language.EN: (
        "This is only a draft. It will not be officially registered until you press “Submit.”"
    ),
}

_SUBMISSION_NOT_CONFIGURED = {
    Language.UZ: (
        "Bu demo rasmiy murojaatni ro'yxatdan o'tkaza olmaydi. "
        "Tasdiqlangan RTMC murojaat kanalidan foydalaning."
    ),
    Language.RU: (
        "Эта демоверсия не может зарегистрировать официальное обращение. "
        "Используйте утверждённый канал обращений RTMC."
    ),
    Language.EN: (
        "This demo cannot register an official appeal. Please use the approved RTMC appeal channel."
    ),
}

_CANCELLED = {
    Language.UZ: ("Mahalliy demo loyihasi bekor qilindi. Hech qanday rasmiy murojaat yaratilmadi."),
    Language.RU: (
        "Локальный демонстрационный проект обращения отменён. Официальное обращение не создавалось."
    ),
    Language.EN: "The local demo draft was cancelled. No official appeal was created.",
}

_CATEGORY_SUBJECTS: dict[Language, dict[Category, str]] = {
    Language.UZ: {
        Category.IMEI: "IMEI bo'yicha murojaat",
        Category.MNP: "MNP bo'yicha murojaat",
        Category.NUMBER_CODES: "Raqam kodlari bo'yicha murojaat",
        Category.NETWORK_QUALITY: "Tarmoq sifati bo'yicha murojaat",
        Category.WEBSITE_ISSUE: "RTMC sayti bo'yicha murojaat",
        Category.OTHER: "Boshqa RTMC masalasi",
    },
    Language.RU: {
        Category.IMEI: "Обращение по IMEI",
        Category.MNP: "Обращение по MNP",
        Category.NUMBER_CODES: "Обращение по кодам нумерации",
        Category.NETWORK_QUALITY: "Обращение по качеству сети",
        Category.WEBSITE_ISSUE: "Обращение по сайту RTMC",
        Category.OTHER: "Другой вопрос RTMC",
    },
    Language.EN: {
        Category.IMEI: "IMEI appeal draft",
        Category.MNP: "MNP appeal draft",
        Category.NUMBER_CODES: "Number codes appeal draft",
        Category.NETWORK_QUALITY: "Network quality appeal draft",
        Category.WEBSITE_ISSUE: "RTMC website issue draft",
        Category.OTHER: "Other RTMC matter",
    },
}


class ComplaintDraftService:
    """Thread-safe, process-local Demo 1 repository.

    All records disappear on restart. The class contains no official backend client
    by design, so even a valid consent event cannot register an appeal.
    """

    def __init__(self, privacy_notice_version: str) -> None:
        self._privacy_notice_version = privacy_notice_version
        self._drafts: dict[UUID, ComplaintDraftReview] = {}
        self._submissions: dict[tuple[UUID, int], tuple[str, ConsentRecord, SubmitResponse]] = {}
        self._lock = RLock()

    def upsert(self, request: DraftUpsertRequest) -> ComplaintDraftReview:
        """Create a draft or apply a version-checked material update."""
        self._validate_fields(request.category, request.fields)
        now = datetime.now(UTC)

        with self._lock:
            if request.draft_id is None:
                if request.expected_version is not None:
                    raise RequestValidationError(
                        "unexpected_version",
                        "expected_version is only valid when updating an existing draft",
                    )
                draft_id = uuid4()
                session_id = request.session_id or uuid4()
                version = 1
                created_at = now
                fields = dict(request.fields)
            else:
                existing = self._get_active(request.draft_id)
                if request.expected_version is None:
                    raise RequestValidationError(
                        "expected_version_required",
                        "expected_version is required when updating a draft",
                    )
                if request.expected_version != existing.version:
                    raise ConflictError(
                        "stale_draft_version",
                        "The draft changed; load the current version before editing",
                    )
                if request.session_id is not None and request.session_id != existing.session_id:
                    raise ConflictError("session_mismatch", "The draft belongs to another session")
                if request.language != existing.language or request.category != existing.category:
                    raise ConflictError(
                        "draft_identity_change",
                        "Language and category cannot be changed by a draft edit",
                    )
                draft_id = existing.draft_id
                session_id = existing.session_id
                version = existing.version + 1
                created_at = existing.created_at
                fields = {**existing.fields, **request.fields}

            review = self._build_review(
                draft_id=draft_id,
                session_id=session_id,
                version=version,
                language=request.language,
                category=request.category,
                fields=fields,
                created_at=created_at,
                updated_at=now,
            )
            self._drafts[draft_id] = review
            return review.model_copy(deep=True)

    def get(self, draft_id: UUID) -> ComplaintDraftReview:
        """Return a defensive copy of the current draft."""
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                raise NotFoundError("draft_not_found", "Complaint draft was not found")
            return draft.model_copy(deep=True)

    def cancel(self, draft_id: UUID) -> ComplaintDraftReview:
        """Cancel a draft; cancelled drafts cannot be edited or submitted."""
        with self._lock:
            draft = self._get_active(draft_id)
            cancelled = draft.model_copy(
                update={"status": DraftStatus.CANCELLED, "updated_at": datetime.now(UTC)}
            )
            self._drafts[draft_id] = cancelled
            return cancelled.model_copy(deep=True)

    def submit(
        self,
        draft_id: UUID,
        request: SubmitRequest,
        request_id: UUID,
    ) -> SubmitResponse:
        """Record exact consent and return a guaranteed non-official result."""
        with self._lock:
            draft = self._get_active(draft_id)
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
            if not draft.complete:
                raise ConflictError(
                    "incomplete_draft",
                    f"The draft is missing required fields: {', '.join(draft.fields_missing)}",
                )

            submission_key = (draft.draft_id, draft.version)
            prior = self._submissions.get(submission_key)
            if prior is not None:
                prior_idempotency_key, _, prior_response = prior
                if prior_idempotency_key != request.idempotency_key:
                    raise ConflictError(
                        "duplicate_submit",
                        "A Submit event was already recorded for this draft version",
                    )
                return prior_response.model_copy(
                    update={"request_id": request_id, "idempotent_replay": True}
                )

            consent = ConsentRecord(
                draft_id=draft.draft_id,
                draft_version=draft.version,
                draft_hash=draft.draft_hash,
                privacy_notice_version=request.privacy_notice_version,
                idempotency_key=request.idempotency_key,
                request_id=request_id,
                recorded_at=datetime.now(UTC),
            )
            response = SubmitResponse(
                request_id=request_id,
                success=False,
                status="official_integration_not_configured",
                officially_registered=False,
                case_number=None,
                message=_SUBMISSION_NOT_CONFIGURED[draft.language],
                idempotent_replay=False,
            )
            self._submissions[submission_key] = (request.idempotency_key, consent, response)
            return response

    def _get_active(self, draft_id: UUID) -> ComplaintDraftReview:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise NotFoundError("draft_not_found", "Complaint draft was not found")
        if draft.status is DraftStatus.CANCELLED:
            raise ConflictError("draft_cancelled", "The complaint draft has been cancelled")
        return draft

    @staticmethod
    def _validate_fields(category: Category, fields: dict[str, str]) -> None:
        allowed = set(REQUIRED_FIELDS[category]) | OPTIONAL_FIELDS
        unsupported = sorted(set(fields) - allowed)
        if unsupported:
            raise RequestValidationError(
                "unsupported_draft_fields",
                f"Unsupported fields for {category.value}: {', '.join(unsupported)}",
            )

    @staticmethod
    def _build_review(
        *,
        draft_id: UUID,
        session_id: UUID,
        version: int,
        language: Language,
        category: Category,
        fields: dict[str, str],
        created_at: datetime,
        updated_at: datetime,
    ) -> ComplaintDraftReview:
        missing = [field for field in REQUIRED_FIELDS[category] if not fields.get(field)]
        subject = fields.get("subject", default_subject_for(language, category))
        description = fields.get("description") or derive_description(fields)
        canonical = json.dumps(
            {
                "version": version,
                "language": language.value,
                "category": category.value,
                "fields": fields,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        draft_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return ComplaintDraftReview(
            draft_id=draft_id,
            session_id=session_id,
            version=version,
            draft_hash=draft_hash,
            status=DraftStatus.ACTIVE,
            language=language,
            category=category,
            subject=subject,
            description=description,
            fields=fields,
            fields_missing=missing,
            personal_data_to_submit=[],
            complete=not missing,
            not_submitted_notice=_NOT_SUBMITTED[language],
            created_at=created_at,
            updated_at=updated_at,
        )

    @staticmethod
    def _derive_description(fields: dict[str, str]) -> str:
        return derive_description(fields)


def missing_fields_for(category: Category) -> list[str]:
    """Expose a copy of category-specific required fields to chat orchestration."""
    return list(REQUIRED_FIELDS[category])


def cancelled_message(language: Language) -> str:
    """Return a localized cancellation result without implying official activity."""
    return _CANCELLED[language]


def default_subject_for(language: Language, category: Category) -> str:
    """Return the existing localized synthetic subject for adapter compatibility."""
    return _CATEGORY_SUBJECTS[language][category]


def derive_description(fields: dict[str, str]) -> str:
    """Derive the existing deterministic review description without mutating fields."""
    preferred = ("impact", "observed_result", "observed_error", "error_message")
    for key in preferred:
        if fields.get(key):
            return fields[key]
    return " | ".join(f"{key}: {value}" for key, value in sorted(fields.items()))


def not_submitted_message(language: Language) -> str:
    """Return the existing non-registration notice for an adapted review."""
    return _NOT_SUBMITTED[language]


def submission_not_configured_message(language: Language) -> str:
    """Return the existing safe local-only submission result wording."""
    return _SUBMISSION_NOT_CONFIGURED[language]
