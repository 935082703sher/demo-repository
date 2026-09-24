"""Extract structured case facts from a free-form user story (IMEI, phase 1).

A deterministic, offline rule extractor turns whatever the user wrote - short,
long, messy, uz/ru/mixed - into typed facts, so the case can be reconstructed
without asking again. It errs toward EXPLICIT only on clear matches and leaves
everything else UNKNOWN (never invented). An LLM extractor can later enrich this
behind the same protocol; the rule extractor stays as a reliable baseline.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

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

# The decision-critical MNP fact schema. Each of the two MNP trees turns on a
# single fact: why an application was rejected, or what the user wants to know.
MNP_FACT_FIELDS = (
    "mnp_rejection_reason",
    "mnp_topic",
)

# (fact, value, patterns) for MNP; more-specific values are listed first so a
# message that mentions documents or balance is not swallowed by the broad
# 'process' intent.
_MNP_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("mnp_rejection_reason", "debt",
     ("qarz", "qarzdor", "dolg", "zadolzhen", "долг", "задолжен")),
    ("mnp_rejection_reason", "data_mismatch",
     ("mos kelma", "mos emas", "notogri malumot", "malumot notogri", "fish",
      "ne sovpad", "dannye ne", "familiya notogri", "ism notogri")),
    ("mnp_rejection_reason", "within_30_days",
     ("30 kun", "30 dan", "oxirgi kochirish", "yaqinda kochir", "30 dney", "otmagan")),
    ("mnp_rejection_reason", "blocked",
     ("raqam bloklangan", "raqam blok", "nomer zablok", "nomer zabl")),
    ("mnp_topic", "documents",
     ("qanday hujjat", "qanaqa hujjat", "hujjatlar kerak", "kerakli hujjat",
      "qaysi hujjat", "kakie dokument", "dokument kerak")),
    ("mnp_topic", "balance",
     ("balans", "balansdagi pul", "pulim koch", "pul koch", "dengi na balanse")),
    ("mnp_topic", "return_operator",
     ("eski operatorga qayt", "ortga qayt", "orqaga qayt", "qaytmoqchi",
      "vernut operator", "obratno")),
    ("mnp_topic", "process",
     ("qanday kochir", "qanaqa kochir", "qanday otkaz", "qanday qilib koch",
      "jarayon", "kak perenes", "kochirmoqchi", "kochirsam", "raqamni koch")),
)

# All rule sets run on every message; namespaced facts keep IMEI/MNP separate.
_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = _IMEI_RULES + _MNP_RULES


class FactExtractor(Protocol):
    """Turn one user message (in the case context) into typed facts."""

    async def extract(self, message: str, case: CaseState, *, turn_id: int) -> list[Fact]: ...


class RuleBasedFactExtractor:
    """Deterministic IMEI/MNP fact extraction; every match is EXPLICIT (user-stated)."""

    async def extract(self, message: str, case: CaseState, *, turn_id: int) -> list[Fact]:
        norm = _normalize(message)
        found: dict[str, str] = {}

        for fact_name, value, patterns in _RULES:
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


ExtractComplete = Callable[[str], Awaitable[str]]

# Allowed values per fact; empty list means free text (e.g. country name).
_ALLOWED_VALUES: dict[str, tuple[str, ...]] = {
    "device_origin": ("local", "imported"),
    "origin_country": (),
    "declaration_status": ("declared", "not_declared"),
    "affected_sim": ("first", "second", "both"),
    "registration_status": ("not_attempted", "attempted", "failed", "success"),
    "previously_working": ("true", "false"),
    "imei_notification_received": ("true", "false"),
    "mnp_rejection_reason": ("data_mismatch", "debt", "within_30_days", "blocked"),
    "mnp_topic": ("process", "documents", "balance", "return_operator"),
}

_LLM_INSTRUCTIONS = (
    "You extract structured IMEI and MNP (number-portability) case facts from a user's "
    "free-form message written in Uzbek, Russian or mixed language, possibly short, "
    "long, messy or misspelled. Understand the meaning, not the exact words. Output a "
    "fact ONLY when the message states or clearly implies it; never invent. Use status "
    "'explicit' when the user stated it directly and 'inferred' when you deduced it from "
    "context. Leave anything unclear out entirely. Respond as JSON: "
    '{"facts": [{"name": ..., "value": ..., "status": "explicit|inferred", '
    '"confidence": 0..1}]}. Allowed names and values: '
    "device_origin(local|imported), origin_country(free text), "
    "declaration_status(declared|not_declared), affected_sim(first|second|both), "
    "registration_status(not_attempted|attempted|failed|success), "
    "previously_working(true|false), imei_notification_received(true|false), "
    "mnp_rejection_reason(data_mismatch|debt|within_30_days|blocked), "
    "mnp_topic(process|documents|balance|return_operator)."
)

_FACTS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string"},
                    "status": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "value", "status", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


class LLMFactExtractor:
    """Semantic IMEI fact extraction via an LLM, with a rule-based safety net.

    Reliable rule matches (EXPLICIT) are always kept; the LLM adds facts the rules
    missed and marks deductions INFERRED. Any LLM failure degrades to rules only.
    """

    def __init__(self, complete: ExtractComplete, fallback: FactExtractor) -> None:
        self._complete = complete
        self._fallback = fallback

    async def extract(self, message: str, case: CaseState, *, turn_id: int) -> list[Fact]:
        rule_facts = await self._fallback.extract(message, case, turn_id=turn_id)
        try:
            raw = await self._complete(self._prompt(message, case))
            llm_facts = self._parse(raw, turn_id)
        except Exception:  # pragma: no cover - network/parse failure -> rules only
            return rule_facts
        merged = {fact.name: fact for fact in rule_facts}
        for fact in llm_facts:
            merged.setdefault(fact.name, fact)  # rule matches are authoritative
        return list(merged.values())

    @staticmethod
    def _prompt(message: str, case: CaseState) -> str:
        return json.dumps(
            {"message": message, "already_known": case.known_facts()}, ensure_ascii=False
        )

    @staticmethod
    def _parse(raw: str, turn_id: int) -> list[Fact]:
        data = json.loads(raw)
        facts: list[Fact] = []
        for item in data.get("facts", []):
            name = str(item.get("name", ""))
            if name not in _ALLOWED_VALUES:
                continue
            value = item.get("value")
            value_str = str(value) if value is not None else None
            allowed = _ALLOWED_VALUES[name]
            if allowed and value_str not in allowed:
                continue
            status = (
                FactStatus.INFERRED
                if str(item.get("status")) == "inferred"
                else FactStatus.EXPLICIT
            )
            confidence = float(item.get("confidence") or 0.8)
            facts.append(
                Fact(
                    name=name,
                    value=value_str,
                    status=status,
                    confidence=max(0.0, min(1.0, confidence)),
                    source="llm",
                    turn_id=turn_id,
                )
            )
        return facts


def build_openai_fact_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> ExtractComplete:
    """Return an OpenAI-backed completion callable for LLM fact extraction."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 500,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "imei_facts",
                    "strict": True,
                    "schema": _FACTS_JSON_SCHEMA,
                }
            },
        }
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            return _extract_output_text(response.json())

    return complete


def _extract_output_text(envelope: dict[str, Any]) -> str:
    for output in envelope.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise ValueError("provider response did not contain output_text")


def detect_domain(message: str) -> str | None:
    """Cheap domain hint for the case (imei / mnp) from the message."""
    norm = _normalize(message)
    imei_terms = ("imei", "royxat", "registratsiya", "qurilma", "telefon", "telfon")
    mnp_terms = ("mnp", "kochir", "operator", "perenos", "raqamni bosh")
    imei_hits = any(term in norm for term in imei_terms)
    mnp_hits = any(term in norm for term in mnp_terms)
    if mnp_hits and not imei_hits:
        return "mnp"
    if imei_hits:
        return "imei"
    return None
