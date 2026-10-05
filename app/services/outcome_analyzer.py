"""Classify how a customer's reply to an offered resolution turned out.

After the assistant offers a resolution card and waits for the result, the next
message says whether it worked. This module turns that free-text reply into a
typed Outcome (success / failure / partial / unclear) with a confidence, any new
facts it reveals, and whether a different problem just appeared.

Two analyzers share one Protocol: a deterministic one (card-specific signals plus
multilingual lexicons, always available and the safety net) and an LLM one that
reads the reply directly and falls back to the deterministic one on low confidence
or any error. Neither may resolve the case - they only classify; the resolution
orchestrator makes the final state transition from this result.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.case_state import CaseState, Fact, FactStatus, Outcome
from app.domain.diagnostics import SuccessCheck
from app.services.fact_extraction import _normalize

# Multilingual signal lexicons for the deterministic fallback (uz/uz-cyrl/ru/en).
_POSITIVE = (
    "ishladi",
    "boldi",
    "tuzaldi",
    "ochildi",
    "hal bol",
    "hal qilindi",
    "rahmat",
    "raxmat",
    "yaxshi",
    "zor",
    "ha ishladi",
    "ha boldi",
    "помогло",
    "заработал",
    "получилось",
    "спасибо",
    "работает",
    "worked",
    "works",
    "fixed",
    "resolved",
    "thanks",
    "solved",
    "done",
)
_NEGATIVE = (
    "ishlamadi",
    "bolmadi",
    "tuzalmadi",
    "ochilmadi",
    "hali ham",
    "xato chiq",
    "xatolik",
    "muammo saqlan",
    "oshamadi",
    "yoq ishlamadi",
    "yana xato",
    "не помогло",
    "не работает",
    "та же ошибка",
    "всё ещё",
    "ошибка",
    "not work",
    "doesnt work",
    "still",
    "same error",
    "error again",
    "nothing happen",
)
_RESIDUAL = ("lekin", "ammo", "biroq", "но", "однако", "but", "however", "endi", "теперь")
_UNCLEAR = (
    "tushunmadim",
    "bilmayman",
    "qanday",
    "qayerni",
    "qaysi",
    "nima qil",
    "не понял",
    "не понимаю",
    "как",
    "куда",
    "which",
    "how do",
    "dont understand",
    "do not understand",
    "confus",
)


@dataclass(frozen=True)
class OutcomeAnalysis:
    """Typed verdict on a customer's reply to an offered resolution."""

    outcome: Outcome
    confidence: float
    reason: str = ""
    new_problem_detected: bool = False
    extracted_facts: list[Fact] = field(default_factory=list)


class OutcomeAnalyzer(Protocol):
    """Classify one reply against the card that was just offered."""

    async def analyze(
        self, reply: str, case: CaseState, *, check: SuccessCheck | None, turn_id: int
    ) -> OutcomeAnalysis: ...


def _signal_hit(text: str, signals: tuple[str, ...] | list[str]) -> bool:
    return any(signal and signal in text for signal in signals)


class RuleOutcomeAnalyzer:
    """Deterministic classifier: card signals first, then multilingual lexicons."""

    async def analyze(
        self, reply: str, case: CaseState, *, check: SuccessCheck | None, turn_id: int
    ) -> OutcomeAnalysis:
        norm = _normalize(reply)
        pos_signals = list(check.positive_signals) if check else []
        neg_signals = list(check.negative_signals) if check else []
        positive = _signal_hit(norm, pos_signals) or _signal_hit(norm, _POSITIVE)
        negative = _signal_hit(norm, neg_signals) or _signal_hit(norm, _NEGATIVE)
        unclear = _signal_hit(norm, _UNCLEAR)
        residual = _signal_hit(norm, _RESIDUAL)

        if positive and (negative or residual):
            return OutcomeAnalysis(
                Outcome.PARTIAL, 0.6, "partial: progress with a remaining issue", True
            )
        if positive and not negative:
            return OutcomeAnalysis(Outcome.SUCCESS, 0.6, "positive signal in reply")
        if negative and not positive:
            return OutcomeAnalysis(Outcome.FAILURE, 0.6, "negative signal in reply")
        if unclear:
            return OutcomeAnalysis(Outcome.UNCLEAR, 0.5, "customer did not understand")
        # No clear signal: do not guess success or failure - ask for clarity.
        return OutcomeAnalysis(Outcome.UNCLEAR, 0.3, "no clear result signal")


AnalyzeComplete = Callable[[str], Awaitable[str]]

_LLM_INSTRUCTIONS = (
    "A customer was given one resolution step for an Uzbek IMEI/MNP issue and has "
    "now replied whether it worked. Classify ONLY the outcome - never decide the "
    "case is closed, that is the server's job. outcome: 'success' (it worked), "
    "'failure' (it did not, the problem remains), 'partial' (it helped but "
    "something is still wrong - often a new sub-problem), 'unclear' (the reply does "
    "not say whether it worked, e.g. the customer did not understand, asked a "
    "question, or changed topic). 'I don't understand' is UNCLEAR, never failure. "
    "Give a confidence 0..1. Set new_problem_detected true only when the reply "
    "describes a different problem than the one being solved. Extract any new fact "
    "the reply states, never invented. Read Uzbek/Russian/mixed and misspelled "
    'text. Respond as JSON: {"outcome": "...", "confidence": 0.0, "reason": "...", '
    '"new_problem_detected": false, "facts": [{"name": ..., "value": ..., '
    '"status": "explicit|inferred", "confidence": 0..1}]}.'
)

_OUTCOME_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["success", "failure", "partial", "unclear"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "new_problem_detected": {"type": "boolean"},
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
        },
    },
    "required": ["outcome", "confidence", "reason", "new_problem_detected", "facts"],
    "additionalProperties": False,
}

# Below this confidence the LLM verdict is not trusted on its own; fall back to the
# deterministic analyzer so a shaky model never drives a state transition.
_MIN_LLM_CONFIDENCE = 0.5


class LLMOutcomeAnalyzer:
    """Classify the reply via an LLM, with the rule analyzer as the safety net."""

    def __init__(self, complete: AnalyzeComplete, fallback: OutcomeAnalyzer) -> None:
        self._complete = complete
        self._fallback = fallback

    async def analyze(
        self, reply: str, case: CaseState, *, check: SuccessCheck | None, turn_id: int
    ) -> OutcomeAnalysis:
        try:
            data = json.loads(await self._complete(self._prompt(reply, case)))
            outcome = Outcome(str(data["outcome"]))
            confidence = float(data.get("confidence", 0.0))
        except Exception:  # pragma: no cover - network/parse failure -> rules
            return await self._fallback.analyze(reply, case, check=check, turn_id=turn_id)
        if confidence < _MIN_LLM_CONFIDENCE:
            return await self._fallback.analyze(reply, case, check=check, turn_id=turn_id)
        facts = _parse_facts(data.get("facts", []), turn_id)
        return OutcomeAnalysis(
            outcome=outcome,
            confidence=confidence,
            reason=str(data.get("reason", "")),
            new_problem_detected=bool(data.get("new_problem_detected", False)),
            extracted_facts=facts,
        )

    @staticmethod
    def _prompt(reply: str, case: CaseState) -> str:
        return json.dumps(
            {
                "reply": reply,
                "resolution_offered": case.resolution_card_id,
                "domain": case.domain,
                "already_known": case.known_facts(),
            },
            ensure_ascii=False,
        )


def _parse_facts(raw: list[dict[str, Any]], turn_id: int) -> list[Fact]:
    facts: list[Fact] = []
    for item in raw:
        name = str(item.get("name", "")).strip()
        value = item.get("value")
        if not name or value is None:
            continue
        status = FactStatus.EXPLICIT if item.get("status") == "explicit" else FactStatus.INFERRED
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        facts.append(
            Fact(
                name=name,
                value=str(value),
                status=status,
                confidence=max(0.0, min(1.0, confidence)),
                source="outcome",
                turn_id=turn_id,
            )
        )
    return facts


def build_openai_outcome_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> AnalyzeComplete:
    """Return an OpenAI-backed completion callable for outcome analysis."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 400,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "outcome_analysis",
                    "strict": True,
                    "schema": _OUTCOME_JSON_SCHEMA,
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
