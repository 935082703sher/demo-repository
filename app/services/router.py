"""Turn router: decide what kind of help a message needs (BLOK 3).

Every turn the user's message is understood holistically and sent to the path
that can actually help it:

* CASE - a concrete IMEI/MNP problem with a resolution path -> the decision-tree
  case engine.
* RAG - an informational / policy / how-much / how-long question -> grounded
  retrieval over the approved knowledge base.
* GREETING - small talk -> a warm reply.

An LLM router understands messy, mixed-language, misspelled input; a deterministic
rule router is the offline safety net and the fallback on any LLM error, so
routing never depends on the model being available.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, Protocol

from app.domain.case_state import CaseState

_WORD = re.compile(r"[a-z0-9]+")

try:  # reuse the KB normalizer for uz-latin/uz-cyrillic/ru folding
    from kb.src.normalize import normalize as _kb_normalize
except Exception:  # pragma: no cover
    _kb_normalize = None


def _normalize(text: str) -> str:
    if _kb_normalize is not None:
        return str(_kb_normalize(text))
    return text.lower()


class Route(StrEnum):
    """Which path should handle this turn."""

    CASE = "case"
    RAG = "rag"
    GREETING = "greeting"


_GREETING_TERMS = (
    "salom", "assalom", "alaykum", "hello", "hi", "hey", "qandaysan", "qalaysan",
    "yaxshimisiz", "rahmat", "tashakkur", "xayr", "privet", "zdravstvuy", "spasibo",
)
# Words that mark an informational question (how much / how long / what / can I…).
_QUESTION_TERMS = (
    "qancha", "narx", "narxi", "necha", "qachon", "qanaqa", "qanday", "nima", "nega",
    "qaysi", "qayer", "kim", "mumkinmi", "kerakmi", "bormi", "boladimi", "qanchaga",
    "skolko", "kak", "kogda", "pochemu", "chto", "gde", "mozhno", "nuzhno", "kakoy",
    "kakie", "nujno",
)
# Words that mark a concrete failure/problem (a case, not a question).
_PROBLEM_TERMS = (
    "ishlamayapti", "ishlamadi", "ishlamay", "otmayapti", "otmadi", "otmay",
    "bolmayapti", "bolmadi", "rad etil", "rad qil", "bloklan", "yoqotdim", "yoqol",
    "ogirla", "muammo", "xato", "chiqmayapti", "kelmayapti", "yoqotil",
    "ne rabotaet", "ne registriruet", "zablokirovan", "poteryal", "ukrali",
    "problema", "oshibka", "otklonili", "otkazil",
)


def _has_any(norm: str, terms: tuple[str, ...]) -> bool:
    return any(term in norm for term in terms)


def _is_greeting(norm: str) -> bool:
    """Greeting terms matched by whole word, so short ones ('hi') don't hit
    unrelated words ('ko'chirmoqchiman' contains 'hi')."""
    for token in _WORD.findall(norm):
        for term in _GREETING_TERMS:
            if token == term or (len(term) >= 4 and (token.startswith(term) or term in token)):
                return True
    return False


class Router(Protocol):
    """Decide the route for one user message in its case context."""

    async def decide(self, message: str, case: CaseState) -> Route: ...


class RuleRouter:
    """Deterministic router: a transparent, offline default and LLM fallback.

    A message with a failure word is a CASE; a question word without a failure is
    RAG; a bare greeting is GREETING; everything else defaults to CASE, so an
    unclear problem still reaches the diagnostic path (which then asks the topic).
    """

    async def decide(self, message: str, case: CaseState) -> Route:
        norm = _normalize(message)
        has_problem = _has_any(norm, _PROBLEM_TERMS)
        has_question = "?" in message or _has_any(norm, _QUESTION_TERMS)
        if not has_problem and not has_question and _is_greeting(norm):
            return Route.GREETING
        if has_question and not has_problem:
            return Route.RAG
        return Route.CASE


RouteComplete = Callable[[str], Awaitable[str]]

_LLM_INSTRUCTIONS = (
    "You route one customer message for an Uzbek telecom assistant (IMEI device "
    "registration and MNP number-portability). Decide which handler should answer, "
    "reading meaning across Uzbek/Russian/mixed and misspelled text. Return exactly "
    'one JSON object: {"route": "case|rag|greeting"}. '
    "'case' = the user reports a concrete problem to diagnose and resolve (device "
    "not registering, blocked, lost/stolen; MNP application rejected; wants to port a "
    "number). 'rag' = an informational question answerable from documents (how much "
    "it costs, how long it takes, what documents are needed, what the law/rule says, "
    "definitions). 'greeting' = small talk with no request. When unsure between case "
    "and rag, prefer 'case'."
)

_ROUTE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"route": {"type": "string", "enum": ["case", "rag", "greeting"]}},
    "required": ["route"],
    "additionalProperties": False,
}


class LLMRouter:
    """Semantic router via an LLM, with the rule router as a safety net.

    The rule router always produces a decision first; the LLM's answer is used only
    when it is a valid route, so any network/parse failure degrades to rules.
    """

    def __init__(self, complete: RouteComplete, fallback: Router) -> None:
        self._complete = complete
        self._fallback = fallback

    async def decide(self, message: str, case: CaseState) -> Route:
        base = await self._fallback.decide(message, case)
        try:
            raw = await self._complete(self._prompt(message, case))
            route = self._parse(raw)
        except Exception:  # pragma: no cover - network/parse failure -> rules
            return base
        return route if route is not None else base

    @staticmethod
    def _prompt(message: str, case: CaseState) -> str:
        return json.dumps(
            {"message": message, "domain": case.domain, "known_facts": case.known_facts()},
            ensure_ascii=False,
        )

    @staticmethod
    def _parse(raw: str) -> Route | None:
        value = str(json.loads(raw).get("route", ""))
        return Route(value) if value in Route._value2member_map_ else None


def build_openai_router_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> RouteComplete:
    """Return an OpenAI-backed completion callable for LLM routing."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 50,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "route",
                    "strict": True,
                    "schema": _ROUTE_JSON_SCHEMA,
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
