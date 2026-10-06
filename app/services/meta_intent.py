"""Recognise conversation acts that are ABOUT the dialogue, not answers within it.

"Muammom bu ro'yxatda yo'q" (my problem is not in this list) is not the answer
"no" to a tree's yes/no question - it rejects the menu. These meta-intents must be
caught before a message is treated as a tree answer or routed by keyword, so the
registration keyword in "ro'yxatda" never pulls a menu rejection into the
registration tree. The caller applies them only when the bot is actually awaiting a
menu choice or a tree answer, so a fresh "telefonim ro'yxatda yo'q" (not registered)
is still handled as a real problem.

normalize() transliterates Cyrillic to Latin and drops apostrophes, so markers are
written in that normalized Latin form.
"""

from __future__ import annotations

from app.services.fact_extraction import _normalize

NONE_OF_ABOVE = "none_of_above"
CORRECTION = "correction"
RESTART = "restart"
OTHER_ISSUE = "other_issue"

_RESTART = (
    "boshidan boshla",
    "qaytadan boshla",
    "qayta boshlaylik",
    "boshidan",
    "restart",
    "s nachala",
    "zanovo",
    "nachnem zanovo",
)
_CORRECTION = (
    "bunday demadim",
    "bunaqa demadim",
    "unday emas",
    "notogri tushun",
    "notogri tushundingiz",
    "men unday",
    "ya ne tak",
    "vy menya ne tak",
    "nepravilno ponyal",
    "ne tak ponyali",
)
_NONE_OF_ABOVE = (
    "royxatda yoq",
    "ruyxatda yoq",
    "menyuda yoq",
    "royxatda yuq",
    "hech biri",
    "hech qaysi",
    "bulardan emas",
    "bularning hech",
    "variantlar mos",
    "mos kelmadi",
    "mos variant yoq",
    "bu royxatda",
    "none of",
    "not in the list",
    "not listed",
    "ne v spiske",
    "ni odin iz",
    "nichego ne podhodit",
)
_OTHER_ISSUE = (
    "boshqa muammo",
    "boshqa savol",
    "yana bir muammo",
    "boshqa masala",
    "drugaya problema",
    "drugoy vopros",
    "other issue",
    "other problem",
)


def conversation_act(message: str) -> str | None:
    """Return the meta-intent of a message (restart/correction/none_of_above/
    other_issue), or None when it is an ordinary problem or answer."""
    norm = _normalize(message)
    if any(term in norm for term in _RESTART):
        return RESTART
    if any(term in norm for term in _CORRECTION):
        return CORRECTION
    if any(term in norm for term in _NONE_OF_ABOVE):
        return NONE_OF_ABOVE
    if any(term in norm for term in _OTHER_ISSUE):
        return OTHER_ISSUE
    return None
