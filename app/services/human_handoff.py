"""Localized human-review and refusal wording."""

from app.domain.enums import EscalationReason, Language

_HUMAN_REVIEW = {
    Language.UZ: (
        "Bu masala mas'ul mutaxassis tomonidan ko'rib chiqilishi kerak. "
        "Men tekshiruv o'tkazmayman va natija yoki muddatni va'da qilmayman."
    ),
    Language.RU: (
        "Этот вопрос требует рассмотрения ответственным специалистом. "
        "Я не провожу расследование и не обещаю результат или срок."
    ),
    Language.EN: (
        "This matter requires review by a responsible specialist. "
        "I do not investigate it or promise an outcome or response time."
    ),
}

_EMERGENCY = {
    Language.UZ: (
        "Men favqulodda xizmat emasman. Agar zudlik bilan xavf mavjud bo'lsa, "
        "RTMC tomonidan tasdiqlangan favqulodda kanalga murojaat qiling. "
        "Bu demoda telefon raqami sozlanmagan."
    ),
    Language.RU: (
        "Я не являюсь экстренной службой. При непосредственной опасности используйте "
        "утверждённый RTMC экстренный канал. В этой демоверсии номер не настроен."
    ),
    Language.EN: (
        "I am not an emergency service. If there is immediate danger, use the "
        "RTMC-approved emergency channel. No emergency number is configured in this demo."
    ),
}

_NO_SOURCE = {
    Language.UZ: (
        "Tasdiqlangan RTMC manbalarida bu ma'lumotni aniqlay olmadim. "
        "Masalani mutaxassisga yo'naltirishim yoki rasmiy murojaat loyihasini "
        "tayyorlashim mumkin."
    ),
    Language.RU: (
        "Мне не удалось подтвердить эту информацию по утверждённым источникам RTMC. "
        "Я могу направить вопрос специалисту или помочь подготовить проект "
        "официального обращения."
    ),
    Language.EN: (
        "I could not confirm this information from approved RTMC sources. "
        "I can route the matter to a specialist or help prepare an official appeal draft."
    ),
}


def handoff_message(language: Language, reason: EscalationReason) -> str:
    """Return restrained wording without invented contacts or queue references."""
    if reason in {
        EscalationReason.EMERGENCY,
        EscalationReason.THREAT_OR_VIOLENCE,
        EscalationReason.SELF_HARM,
    }:
        return _EMERGENCY[language]
    if reason is EscalationReason.NO_APPROVED_SOURCE:
        return _NO_SOURCE[language]
    return _HUMAN_REVIEW[language]
