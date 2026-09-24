"""Combined per-turn understanding: routing + fact extraction in one LLM call.

Routing (BLOK 3) and fact extraction (BLOK 1) both read the same message, so a
single LLM call returns both the route and the facts, halving the model round
trips per turn. A deterministic analyzer (rule router + rule extractor, both
offline) is the safety net and the fallback on any LLM error, and reliable rule
facts always override the LLM's, exactly as the standalone extractor does.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.case_state import CaseState, Fact
from app.services.fact_extraction import RuleBasedFactExtractor, parse_llm_facts
from app.services.router import Route, RuleRouter


@dataclass(frozen=True)
class TurnAnalysis:
    """What one turn's message means: its route and any extracted facts."""

    route: Route
    facts: list[Fact]


class TurnAnalyzer(Protocol):
    """Understand one message in its case context (route + facts)."""

    async def analyze(self, message: str, case: CaseState, *, turn_id: int) -> TurnAnalysis: ...


class RuleTurnAnalyzer:
    """Deterministic analyzer: the rule router and rule extractor, both offline."""

    def __init__(self) -> None:
        self._router = RuleRouter()
        self._extractor = RuleBasedFactExtractor()

    async def analyze(self, message: str, case: CaseState, *, turn_id: int) -> TurnAnalysis:
        facts = await self._extractor.extract(message, case, turn_id=turn_id)
        route = await self._router.decide(message, case)
        return TurnAnalysis(route=route, facts=facts)


AnalyzeComplete = Callable[[str], Awaitable[str]]

_LLM_INSTRUCTIONS = (
    "You analyse one customer message for an Uzbek telecom assistant (IMEI device "
    "registration and MNP number portability), reading meaning across "
    "Uzbek/Russian/mixed and misspelled text. Do TWO things in one JSON object.\n"
    "1) route: 'case' = a concrete problem to diagnose and resolve (device not "
    "registering, blocked, lost/stolen; MNP application rejected; wants to port a "
    "number); 'rag' = an informational question answerable from documents (cost, "
    "duration, needed documents, what the law/rule says, definitions); 'greeting' = "
    "small talk. When unsure between case and rag, prefer 'case'.\n"
    "2) facts: output a fact ONLY when the message states or clearly implies it; "
    "never invent. status 'explicit' if stated directly, 'inferred' if deduced. "
    "Allowed names and values: device_origin(local|imported), origin_country(free "
    "text), declaration_status(declared|not_declared), affected_sim(first|second|"
    "both), registration_status(not_attempted|attempted|failed|success), "
    "previously_working(true|false), imei_notification_received(true|false), "
    "mnp_rejection_reason(data_mismatch|debt|within_30_days|blocked), "
    "mnp_topic(process|documents|balance|return_operator).\n"
    'Respond as JSON: {"route": "case|rag|greeting", "facts": [{"name": ..., '
    '"value": ..., "status": "explicit|inferred", "confidence": 0..1}]}.'
)

_ANALYSIS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["case", "rag", "greeting"]},
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
    "required": ["route", "facts"],
    "additionalProperties": False,
}


class LLMTurnAnalyzer:
    """One LLM call for route + facts, with the rule analyzer as a safety net."""

    def __init__(self, complete: AnalyzeComplete, fallback: RuleTurnAnalyzer) -> None:
        self._complete = complete
        self._fallback = fallback
        self._rule_extractor = RuleBasedFactExtractor()
        self._rule_router = RuleRouter()

    async def analyze(self, message: str, case: CaseState, *, turn_id: int) -> TurnAnalysis:
        rule_facts = await self._rule_extractor.extract(message, case, turn_id=turn_id)
        try:
            data = json.loads(await self._complete(self._prompt(message, case)))
            llm_facts = parse_llm_facts(data.get("facts", []), turn_id)
            route_value = str(data.get("route", ""))
        except Exception:  # pragma: no cover - network/parse failure -> rules
            return await self._fallback.analyze(message, case, turn_id=turn_id)
        # Rule matches are authoritative; the LLM only adds facts the rules missed.
        merged = {fact.name: fact for fact in rule_facts}
        for fact in llm_facts:
            merged.setdefault(fact.name, fact)
        if route_value in Route._value2member_map_:
            route = Route(route_value)
        else:
            route = await self._rule_router.decide(message, case)
        return TurnAnalysis(route=route, facts=list(merged.values()))

    @staticmethod
    def _prompt(message: str, case: CaseState) -> str:
        return json.dumps(
            {"message": message, "domain": case.domain, "already_known": case.known_facts()},
            ensure_ascii=False,
        )


def build_openai_turn_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> AnalyzeComplete:
    """Return an OpenAI-backed completion callable for combined turn analysis."""
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
                    "name": "turn_analysis",
                    "strict": True,
                    "schema": _ANALYSIS_JSON_SCHEMA,
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
