"""Extract structured case facts from a free-form user story (IMEI, phase 1).

A deterministic, offline rule extractor turns whatever the user wrote - short,
long, messy, uz/ru/mixed - into typed facts, so the case can be reconstructed
without asking again. It errs toward EXPLICIT only on clear matches and leaves
everything else UNKNOWN (never invented). An LLM extractor can later enrich this
behind the same protocol; the rule extractor stays as a reliable baseline.
"""

from __future__ import annotations

from typing import Protocol

from app.domain.case_state import CaseState, Fact, FactStatus

try:  # reuse the KB normalizer for uz-latin/uz-cyrillic/ru folding
    from kb.src.normalize import normalize as _kb_normalize
except Exception:  # pragma: no cover
    _kb_normalize = None


def _normalize(text: str) -> str:
    if _kb_normalize is not None:
        return str(_kb_normalize(text))
    return text.lower()


# The decision-critical IMEI fact schema (used by later missing-fact reasoning).
IMEI_FACT_FIELDS = (
    "device_origin",
    "origin_country",
    "declaration_status",
    "affected_sim",
    "registration_status",
    "previously_working",
    "imei_notification_received",
)

# (fact, value, patterns) — first matching value per fact wins, so order
# more-specific/more-informative values first.
_IMEI_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("device_origin", "imported",
     ("chetdan", "chet el", "xorij", "olib kel", "dubay", "import", "privoz",
      "zagranits", "turkiya", "xitoy", "amerika", "rossiya")),
    ("device_origin", "local",
     ("ozbekistondan", "dokon", "magazin", "mahalliy", "shu yerdan")),
    ("declaration_status", "not_declared",
     ("deklaratsiya qilma", "deklaratsiyasiz", "deklaratsiya yoq", "bez deklaratsi")),
    ("declaration_status", "declared",
     ("deklaratsiya qildim", "deklaratsiyadan otk", "kirim orderi", "bojxonadan otk")),
    ("affected_sim", "both", ("ikkala sim", "har ikki sim")),
    ("affected_sim", "second",
     ("ikkinchi sim", "2 sim", "2-sim", "vtoroy sim", "ikkinchi simkarta")),
    ("affected_sim", "first", ("birinchi sim", "1 sim", "1-sim")),
    ("registration_status", "success",
     ("royxatdan otdi", "royxatga olindi", "muvaffaqiyatli royxat")),
    ("registration_status", "failed",
     ("royxatdan otma", "royxatga olinmadi", "registratsiya xato", "otmadi", "bolmadi")),
    ("registration_status", "attempted",
     ("royxatdan otkaz", "registratsiya qil", "saytda", "royxatdan otmoqchi")),
    ("previously_working", "true",
     ("avval ishla", "oldin ishla", "ishlayotgandi", "ishlagan")),
    ("previously_working", "false",
     ("hech qachon ishlamadi", "boshidan ishlamadi", "umuman ishlamadi")),
)

_COUNTRIES = {
    "dubay": "UAE", "turkiya": "Turkey", "xitoy": "China",
    "amerika": "USA", "rossiya": "Russia",
}


class FactExtractor(Protocol):
    """Turn one user message (in the case context) into typed facts."""

    def extract(self, message: str, case: CaseState, *, turn_id: int) -> list[Fact]: ...


class RuleBasedFactExtractor:
    """Deterministic IMEI fact extraction; every match is EXPLICIT (user-stated)."""

    def extract(self, message: str, case: CaseState, *, turn_id: int) -> list[Fact]:
        norm = _normalize(message)
        found: dict[str, str] = {}

        for fact_name, value, patterns in _IMEI_RULES:
            if fact_name in found:
                continue
            if any(pattern in norm for pattern in patterns):
                found[fact_name] = value

        if found.get("device_origin") == "imported" and "origin_country" not in found:
            for token, country in _COUNTRIES.items():
                if token in norm:
                    found["origin_country"] = country
                    break

        if "imei" in norm and ("sms" in norm or "xabar" in norm) and "kel" in norm:
            found["imei_notification_received"] = "true"

        return [
            Fact(name=name, value=value, status=FactStatus.EXPLICIT, source="user", turn_id=turn_id)
            for name, value in found.items()
        ]


def detect_domain(message: str) -> str | None:
    """Cheap domain hint for the case (imei / mnp) from the message."""
    norm = _normalize(message)
    imei_terms = ("imei", "royxat", "registratsiya", "qurilma", "telefon")
    mnp_terms = ("mnp", "kochir", "operator", "perenos", "raqamni bosh")
    imei_hits = any(term in norm for term in imei_terms)
    mnp_hits = any(term in norm for term in mnp_terms)
    if mnp_hits and not imei_hits:
        return "mnp"
    if imei_hits:
        return "imei"
    return None
