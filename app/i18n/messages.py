"""Approved initial Demo 2 citizen-facing messages."""

from app.domain.enums import Language

OUT_OF_SCOPE = {
    Language.UZ: (
        "Men RTMCning telekommunikatsiya bo‘yicha AI yordamchisiman va faqat RTMC "
        "xizmatlari hamda telekommunikatsiyaga oid savollarga yordam bera olaman. "
        "RTMCga oid savolingiz bo‘lsa, mamnuniyat bilan yordam beraman."
    ),
    Language.RU: (
        "Я — ИИ-помощник RTMC и могу помогать только по вопросам услуг RTMC и "
        "телекоммуникаций. Я буду рад помочь с вопросом, относящимся к RTMC."
    ),
    Language.EN: (
        "I’m the RTMC telecommunications AI assistant and can only help with RTMC "
        "services and telecommunications-related questions. I’d be glad to help "
        "with an RTMC-related query."
    ),
}


def out_of_scope_message(language: Language) -> str:
    """Return exactly one localized scope refusal."""
    return OUT_OF_SCOPE[language]


_USAGE_LIMIT_BOTH = {
    Language.UZ: (
        "Ushbu suhbat uchun AI so‘rovlar limitiga yetdingiz. Qo‘shimcha yordam "
        "uchun {phone} raqamiga qo‘ng‘iroq qiling yoki RTMCning rasmiy aloqa "
        "sahifasidan foydalaning: {url}."
    ),
    Language.RU: (
        "Вы достигли лимита запросов к ИИ для этого сеанса. Для дополнительной "
        "помощи позвоните по номеру {phone} или воспользуйтесь официальной "
        "страницей связи RTMC: {url}."
    ),
    Language.EN: (
        "You have reached the AI request limit for this session. For additional "
        "help, call {phone} or use RTMC’s official contact page: {url}."
    ),
}

_USAGE_LIMIT_URL = {
    Language.UZ: (
        "Ushbu suhbat uchun AI so‘rovlar limitiga yetdingiz. Qo‘shimcha yordam "
        "uchun RTMCning rasmiy aloqa sahifasidan foydalaning: {url}."
    ),
    Language.RU: (
        "Вы достигли лимита запросов к ИИ для этого сеанса. Для дополнительной "
        "помощи воспользуйтесь официальной страницей связи RTMC: {url}."
    ),
    Language.EN: (
        "You have reached the AI request limit for this session. For additional "
        "help, use RTMC’s official contact page: {url}."
    ),
}

_USAGE_LIMIT_NEUTRAL = {
    Language.UZ: (
        "Ushbu suhbat uchun AI so‘rovlar limitiga yetdingiz. Qo‘shimcha yordam "
        "uchun inson operatoriga yo‘naltirishni so‘rashingiz mumkin."
    ),
    Language.RU: (
        "Вы достигли лимита запросов к ИИ для этого сеанса. Вы можете запросить "
        "передачу вопроса оператору."
    ),
    Language.EN: (
        "You have reached the AI request limit for this session. You may request "
        "a human-operator handoff for additional help."
    ),
}

_RATE_LIMIT = {
    Language.UZ: "Juda ko‘p so‘rov yuborildi. {seconds} soniyadan keyin qayta urinib ko‘ring.",
    Language.RU: "Отправлено слишком много запросов. Повторите попытку через {seconds} сек.",
    Language.EN: "Too many requests were sent. Try again in {seconds} seconds.",
}


def usage_limit_message(language: Language, phone: str | None, url: str | None) -> str:
    """Render only configured, approved contact values."""
    if phone and url:
        return _USAGE_LIMIT_BOTH[language].format(phone=phone, url=url)
    if url:
        return _USAGE_LIMIT_URL[language].format(url=url)
    return _USAGE_LIMIT_NEUTRAL[language]


def rate_limit_message(language: Language, retry_after_seconds: int) -> str:
    """Return a localized request-rate response with retry guidance."""
    return _RATE_LIMIT[language].format(seconds=retry_after_seconds)
