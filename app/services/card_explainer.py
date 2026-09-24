"""Explain an approved resolution card in natural language (BLOK 4).

The decision engine chooses the resolution and the knowledge base proves it; here
the LLM only *explains* it. It rephrases the card's probable cause into warm,
situation-aware language, strictly from the approved wording - it never touches
the action steps, the official link or the contact (those are composed
deterministically by the caller) and it invents no new fact. Any LLM failure
falls back to the card's own cause text, so the answer is always grounded.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.domain.case_state import CaseState


class CardExplainer(Protocol):
    """Turn an approved probable-cause into a natural explanation."""

    async def explain(self, cause: str, case: CaseState, lang: str) -> str: ...


class TemplateCardExplainer:
    """Deterministic explainer: the card's own cause text, unchanged."""

    async def explain(self, cause: str, case: CaseState, lang: str) -> str:
        return cause


ExplainComplete = Callable[[str], Awaitable[str]]

_LANGUAGE_NAME = {"uz": "Uzbek", "ru": "Russian", "en": "English"}

_LLM_INSTRUCTIONS = (
    "You are a calm, helpful telecom support agent. You are given the APPROVED "
    "explanation of why a customer's IMEI/MNP case turned out the way it did, plus "
    "the facts already known about their situation. Rewrite the explanation so it "
    "reads warm, clear and personal, in the requested language. Rules: use ONLY the "
    "given explanation and facts; do NOT add or change any step, fee, deadline, "
    "phone number, link or legal detail; do NOT invent anything; keep it to two or "
    "three short sentences and do not list action steps (those are shown "
    'separately). Respond as JSON: {"explanation": "..."}.'
)

_EXPLAIN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"explanation": {"type": "string"}},
    "required": ["explanation"],
    "additionalProperties": False,
}


class LLMCardExplainer:
    """Rephrase the approved cause via an LLM, with a deterministic safety net."""

    def __init__(self, complete: ExplainComplete, fallback: CardExplainer) -> None:
        self._complete = complete
        self._fallback = fallback

    async def explain(self, cause: str, case: CaseState, lang: str) -> str:
        try:
            raw = await self._complete(self._prompt(cause, case, lang))
            text = str(json.loads(raw).get("explanation", "")).strip()
        except Exception:  # pragma: no cover - network/parse failure -> approved text
            return await self._fallback.explain(cause, case, lang)
        return text or await self._fallback.explain(cause, case, lang)

    @staticmethod
    def _prompt(cause: str, case: CaseState, lang: str) -> str:
        return json.dumps(
            {
                "language": _LANGUAGE_NAME.get(lang, "Uzbek"),
                "approved_explanation": cause,
                "known_facts": case.known_facts(),
            },
            ensure_ascii=False,
        )


def build_openai_card_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> ExplainComplete:
    """Return an OpenAI-backed completion callable for card explanation."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 300,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "card_explanation",
                    "strict": True,
                    "schema": _EXPLAIN_JSON_SCHEMA,
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
