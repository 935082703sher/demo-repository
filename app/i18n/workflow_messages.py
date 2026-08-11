"""Synthetic Stage 3A message fixtures; public wording is not approved."""

from app.domain.complaint_workflow import MessageKey
from app.domain.enums import Language

SYNTHETIC_WORKFLOW_MESSAGES: dict[Language, dict[MessageKey, str]] = {
    Language.UZ: {
        MessageKey.CLARIFICATION_REQUIRED: "[SINTETIK] Tasnifni aniqlashtirish kerak.",
        MessageKey.MISSING_FIELDS: "[SINTETIK] Loyiha uchun ma'lumot yetishmaydi.",
        MessageKey.HUMAN_REVIEW_REQUIRED: "[SINTETIK] Inson ko'rigi talab qilinadi.",
        MessageKey.SENSITIVE_DATA_WARNING: "[SINTETIK] Maxfiy qiymatni chatga yozmang.",
        MessageKey.DRAFT_READY: "[SINTETIK] Loyiha ko'rib chiqishga tayyor.",
        MessageKey.CONSENT_REQUIRED: "[SINTETIK] Joriy loyiha uchun rozilik talab qilinadi.",
        MessageKey.CONSENT_INVALIDATED: "[SINTETIK] Tahrirdan keyin oldingi rozilik bekor.",
        MessageKey.SUBMISSION_UNAVAILABLE: "[SINTETIK] Rasmiy yuborish sozlanmagan.",
        MessageKey.CANCELLED: "[SINTETIK] Mahalliy loyiha bekor qilindi.",
        MessageKey.UNSUPPORTED_AUTHORITY_REQUEST: (
            "[SINTETIK] Tasdiqlangan vakolatli ma'lumot mavjud emas."
        ),
    },
    Language.RU: {
        MessageKey.CLARIFICATION_REQUIRED: "[СИНТЕТИКА] Требуется уточнить классификацию.",
        MessageKey.MISSING_FIELDS: "[СИНТЕТИКА] Для проекта не хватает данных.",
        MessageKey.HUMAN_REVIEW_REQUIRED: "[СИНТЕТИКА] Требуется проверка человеком.",
        MessageKey.SENSITIVE_DATA_WARNING: "[СИНТЕТИКА] Не вводите секретное значение в чат.",
        MessageKey.DRAFT_READY: "[СИНТЕТИКА] Проект готов к проверке.",
        MessageKey.CONSENT_REQUIRED: "[СИНТЕТИКА] Требуется согласие на текущий проект.",
        MessageKey.CONSENT_INVALIDATED: "[СИНТЕТИКА] Изменение отменило прежнее согласие.",
        MessageKey.SUBMISSION_UNAVAILABLE: "[СИНТЕТИКА] Официальная отправка не настроена.",
        MessageKey.CANCELLED: "[СИНТЕТИКА] Локальный проект отменён.",
        MessageKey.UNSUPPORTED_AUTHORITY_REQUEST: (
            "[СИНТЕТИКА] Утверждённая информация отсутствует."
        ),
    },
    Language.EN: {
        MessageKey.CLARIFICATION_REQUIRED: "[SYNTHETIC] Classification needs clarification.",
        MessageKey.MISSING_FIELDS: "[SYNTHETIC] The draft is missing information.",
        MessageKey.HUMAN_REVIEW_REQUIRED: "[SYNTHETIC] Human review is required.",
        MessageKey.SENSITIVE_DATA_WARNING: "[SYNTHETIC] Do not enter a secret value in chat.",
        MessageKey.DRAFT_READY: "[SYNTHETIC] The draft is ready for review.",
        MessageKey.CONSENT_REQUIRED: "[SYNTHETIC] Consent is required for this draft.",
        MessageKey.CONSENT_INVALIDATED: "[SYNTHETIC] Editing invalidated earlier consent.",
        MessageKey.SUBMISSION_UNAVAILABLE: "[SYNTHETIC] Official submission is unavailable.",
        MessageKey.CANCELLED: "[SYNTHETIC] The local draft was cancelled.",
        MessageKey.UNSUPPORTED_AUTHORITY_REQUEST: (
            "[SYNTHETIC] Approved authoritative information is unavailable."
        ),
    },
}


def synthetic_workflow_message(language: Language, key: MessageKey) -> str:
    """Return a same-language synthetic fixture without language detection."""
    return SYNTHETIC_WORKFLOW_MESSAGES[language][key]
