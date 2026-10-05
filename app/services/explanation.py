"""Adapt HOW a resolution is explained to the customer; never WHAT it says.

The approved facts and steps are fixed. This module reads cues in the customer's
words to pick an explanation style, and escalates the style when the customer keeps
not understanding, so the same wording is never simply repeated: first simpler,
then step-by-step, then with an example. The style is stored on the case's
explanation profile and read by the explainers; the re-explanation lead-ins here
guarantee the text differs even with the deterministic (template) explainer.
"""

from __future__ import annotations

from app.domain.case_state import ExplanationStyle
from app.services.fact_extraction import _normalize

# Cue -> style, checked in order; first match wins. Covers uz/uz-cyrl-ish/ru/en.
_STYLE_CUES: list[tuple[ExplanationStyle, tuple[str, ...]]] = [
    (ExplanationStyle.VISUAL, ("rasm", "skrinshot", "screenshot", "foto", "картинк", "фото")),
    (
        ExplanationStyle.REASSURING,
        ("qorq", "xavotir", "tashvish", "боюсь", "волну", "worried", "afraid", "nervous"),
    ),
    (ExplanationStyle.EXAMPLE, ("misol", "namuna", "пример", "example", "for instance")),
    (
        ExplanationStyle.STEP_BY_STEP,
        (
            "qayerni bos",
            "qadam",
            "bosqich",
            "qanday qila",
            "по шаг",
            "пошагов",
            "step by step",
            "where do i",
            "where to",
        ),
    ),
    (
        ExplanationStyle.DETAILED,
        ("nega", "sabab", "batafsil", "почему", "подробно", "why", "in detail"),
    ),
    (
        ExplanationStyle.CONCISE,
        ("qisqa", "tez ayt", "короче", "кратко", "briefly", "short answer", "make it short"),
    ),
    (
        ExplanationStyle.TECHNICAL,
        ("texnik", "api", "http", "error code", "xato kodi", "код ошибки", "log", "технич"),
    ),
    (
        ExplanationStyle.SIMPLE,
        (
            "tushunmadim",
            "oddiy",
            "sodda",
            "не понял",
            "не понимаю",
            "проще",
            "simple",
            "simpler",
            "dont understand",
            "do not understand",
        ),
    ),
]


def detect_style(message: str) -> ExplanationStyle | None:
    """Return the explanation style the customer's words ask for, or None."""
    norm = _normalize(message)
    for style, cues in _STYLE_CUES:
        if any(cue in norm for cue in cues):
            return style
    return None


def style_for_confusion(count: int) -> ExplanationStyle:
    """Escalate the style the more times the customer has not understood."""
    if count <= 1:
        return ExplanationStyle.SIMPLE
    if count == 2:
        return ExplanationStyle.STEP_BY_STEP
    return ExplanationStyle.EXAMPLE


# A fresh lead-in per re-explanation so the message is never byte-identical, even
# when the template explainer returns the same approved cause text.
_REEXPLAIN_LEADIN = {
    "uz": {
        ExplanationStyle.SIMPLE: "Boshqacha, oddiyroq aytaman:",
        ExplanationStyle.STEP_BY_STEP: "Keling, bitta-bitta qadam bilan ko'rib chiqamiz:",
        ExplanationStyle.EXAMPLE: "Oddiy misol bilan tushuntiraman:",
    },
    "uz_cyrl": {
        ExplanationStyle.SIMPLE: "Бошқача, оддийроқ айтаман:",
        ExplanationStyle.STEP_BY_STEP: "Келинг, битта-битта қадам билан кўриб чиқамиз:",
        ExplanationStyle.EXAMPLE: "Оддий мисол билан тушунтираман:",
    },
    "ru": {
        ExplanationStyle.SIMPLE: "Скажу иначе, проще:",
        ExplanationStyle.STEP_BY_STEP: "Давайте по шагам, по одному:",
        ExplanationStyle.EXAMPLE: "Объясню на простом примере:",
    },
    "en": {
        ExplanationStyle.SIMPLE: "Let me put it more simply:",
        ExplanationStyle.STEP_BY_STEP: "Let's go one step at a time:",
        ExplanationStyle.EXAMPLE: "Here's a simple example:",
    },
    "kaa": {
        ExplanationStyle.SIMPLE: "Basqasha, ápiwayıraq aytaman:",
        ExplanationStyle.STEP_BY_STEP: "Keling, birme-bir qádem menen qarayıq:",
        ExplanationStyle.EXAMPLE: "Ápiwayı mısal menen túsindiremen:",
    },
}


def reexplain_leadin(style: ExplanationStyle, lang: str) -> str:
    """A short lead-in that marks this as a fresh, different explanation."""
    by_lang = _REEXPLAIN_LEADIN.get(lang, _REEXPLAIN_LEADIN["uz"])
    return by_lang.get(style, by_lang[ExplanationStyle.SIMPLE])
