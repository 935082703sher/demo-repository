"""Versioned synthetic follow-up questions selected only by server rules."""

from __future__ import annotations

from typing import Final

from app.domain.enums import Language

FOLLOW_UP_QUESTION_SET_VERSION: Final = "synthetic-stage3c-follow-up-v1"

_QUESTIONS: dict[Language, dict[str, str]] = {
    Language.EN: {
        "applicant_type": (
            "[SYNTHETIC] Are you an individual, legal entity, or authorized representative?"
        ),
        "appeal_kind": "[SYNTHETIC] Is this an application, proposal, or complaint?",
        "subcategory": "[SYNTHETIC] Which service issue best describes this request?",
        "operator": "[SYNTHETIC] Which operator provides the affected service?",
        "service_type": "[SYNTHETIC] Which service is affected?",
        "region": "[SYNTHETIC] Which region or province is affected?",
        "district": "[SYNTHETIC] Which district or city is affected?",
        "approximate_location": (
            "[SYNTHETIC] What is the approximate location, without a residential address?"
        ),
        "event_time": "[SYNTHETIC] When did the issue occur?",
        "frequency": "[SYNTHETIC] How often does it occur?",
        "duration": "[SYNTHETIC] How long does each occurrence last?",
        "impact": "[SYNTHETIC] What service impact did you observe?",
    },
    Language.UZ: {
        "applicant_type": "[SINTETIK] Siz jismoniy shaxs, yuridik shaxs yoki vakilmisiz?",
        "appeal_kind": "[SINTETIK] Bu ariza, taklif yoki shikoyatmi?",
        "subcategory": "[SINTETIK] Qaysi xizmat muammosi murojaatni aniqroq ifodalaydi?",
        "operator": "[SINTETIK] Ta'sirlangan xizmatni qaysi operator ko'rsatadi?",
        "service_type": "[SINTETIK] Qaysi xizmat ta'sirlangan?",
        "region": "[SINTETIK] Qaysi viloyat yoki hudud ta'sirlangan?",
        "district": "[SINTETIK] Qaysi tuman yoki shahar ta'sirlangan?",
        "approximate_location": "[SINTETIK] Uy manzilisiz taxminiy joylashuvni ko'rsating.",
        "event_time": "[SINTETIK] Muammo qachon yuz berdi?",
        "frequency": "[SINTETIK] Muammo qanchalik tez-tez takrorlanadi?",
        "duration": "[SINTETIK] Har bir holat qancha davom etadi?",
        "impact": "[SINTETIK] Xizmatga qanday ta'sir kuzatildi?",
    },
    Language.RU: {
        "applicant_type": "[СИНТЕТИКА] Вы физическое лицо, юридическое лицо или представитель?",
        "appeal_kind": "[СИНТЕТИКА] Это заявление, предложение или жалоба?",
        "subcategory": "[СИНТЕТИКА] Какая проблема с услугой точнее описывает обращение?",
        "operator": "[СИНТЕТИКА] Какой оператор предоставляет затронутую услугу?",
        "service_type": "[СИНТЕТИКА] Какая услуга затронута?",
        "region": "[СИНТЕТИКА] Какая область или регион затронуты?",
        "district": "[СИНТЕТИКА] Какой район или город затронуты?",
        "approximate_location": "[СИНТЕТИКА] Укажите примерное место без домашнего адреса.",
        "event_time": "[СИНТЕТИКА] Когда возникла проблема?",
        "frequency": "[СИНТЕТИКА] Как часто возникает проблема?",
        "duration": "[СИНТЕТИКА] Как долго длится каждый случай?",
        "impact": "[СИНТЕТИКА] Какое влияние на услугу Вы наблюдали?",
    },
}


def follow_up_question(language: Language, field_key: str) -> tuple[str, str]:
    """Return a stable version-qualified key and same-language synthetic wording."""
    question = _QUESTIONS[language].get(field_key)
    selected_key = field_key if question is not None else "subcategory"
    return (
        f"{FOLLOW_UP_QUESTION_SET_VERSION}.{selected_key}",
        question or _QUESTIONS[language]["subcategory"],
    )
