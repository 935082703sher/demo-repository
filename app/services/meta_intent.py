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


# A standalone informational/pricing question - the sign of a new complete request
# rather than an answer to a pending "send the error text" style question.
_QUESTION_MARKERS = (
    "qancha",
    "narx",
    "necha",
    "qanchaga",
    "mumkinmi",
    "qachon",
    "qanaqa narx",
    "how much",
    "price",
    "cost",
    "skolko",
    "stoit",
    "tsena",
)
# Words that mark an actual error/evidence answer, so it is NOT a new request.
_EVIDENCE_MARKERS = (
    "xato",
    "xatolik",
    "error",
    "oshibka",
    "chiqdi",
    "chiqyapti",
    "yozilgan",
    "yozib",
    "kod",
    "skrinshot",
    "screenshot",
    "sms",
    "ekranda",
    "deb chiq",
    "blok",
)


# "Is X allowed / possible?" markers. These signal a permission/possibility question
# that wants a reasoned legal answer, not a diagnostic walk - distinct from "nima
# qilay" (what do I do) or "kim javobgar" (who), which a tree can handle.
_PERMISSION_MARKERS = (
    "boladimi",
    "bolarmikan",
    "mumkinmi",
    "mumkin mi",
    "mumkinmikan",
    "maylimi",
    "ruxsatmi",
    "ruxsat beriladimi",
    "qilsa boladi",
    "qilsak boladi",
    "qilish mumkinmi",
    "mozhno li",
    "razreshaetsya li",
    "is it allowed",
    "is it possible",
    "can i",
    "can we",
)


def is_permission_question(message: str) -> bool:
    """True when the message asks whether something is allowed or possible.

    Such a question wants the reasoning engine to apply the law and answer, not a
    diagnostic tree that gathers a fact - so the caller prefers the grounded policy
    answer over walking a tree even when a tree's keywords match.
    """
    return any(marker in _normalize(message) for marker in _PERMISSION_MARKERS)


def is_new_request(message: str) -> bool:
    """True when a message is a new, self-contained request, not an answer to the
    pending question - e.g. a standalone pricing question while the bot is waiting
    for an error text. A short error description or a plain yes/no is not one."""
    norm = _normalize(message)
    has_question = ("?" in message) or any(m in norm for m in _QUESTION_MARKERS)
    has_evidence = any(m in norm for m in _EVIDENCE_MARKERS)
    if has_evidence:
        return False
    if has_question:
        return True
    # A long message that introduces a new scenario (and gives no error text) is new.
    return len(norm.split()) >= 18


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
