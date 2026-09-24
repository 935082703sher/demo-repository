"""Rephrase a diagnostic question naturally (BLOK 4, questions).

The decision tree still decides WHICH question to ask and keeps its exact answer
options; this only makes the question text itself read warm and situation-aware
instead of like a fixed form field. The options (the buttons) are never touched,
so answer mapping is unaffected, and any LLM failure falls back to the tree's own
wording. It never invents facts or adds choices.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.domain.case_state import CaseState


class QuestionExplainer(Protocol):
    """Turn an approved question into a natural, situation-aware question."""

    async def explain(self, question: str, case: CaseState, lang: str) -> str: ...


class TemplateQuestionExplainer:
    """Deterministic explainer: the tree's own question text, unchanged."""

    async def explain(self, question: str, case: CaseState, lang: str) -> str:
        return question


ExplainComplete = Callable[[str], Awaitable[str]]

_LANGUAGE_NAME = {"uz": "Uzbek", "ru": "Russian", "en": "English"}

_LLM_INSTRUCTIONS = (
    "You are a calm, helpful telecom support agent gathering information. You are "
    "given the next diagnostic QUESTION to ask the customer and the facts already "
    "known about their situation. Rewrite the question so it reads warm and natural "
    "in the requested language, acknowledging what is already known in at most one "
    "short clause. Rules: keep it ONE question with the same meaning; do NOT list, "
    "add, remove or rename any answer option (the choices are shown as separate "
    "buttons); do NOT invent facts; keep it short. Respond as JSON: "
    '{"question": "..."}.'
)

_QUESTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"question": {"type": "string"}},
    "required": ["question"],
    "additionalProperties": False,
}


class LLMQuestionExplainer:
    """Rephrase the approved question via an LLM, with a deterministic safety net."""

    def __init__(self, complete: ExplainComplete, fallback: QuestionExplainer) -> None:
        self._complete = complete
        self._fallback = fallback

    async def explain(self, question: str, case: CaseState, lang: str) -> str:
        try:
            raw = await self._complete(self._prompt(question, case, lang))
            text = str(json.loads(raw).get("question", "")).strip()
        except Exception:  # pragma: no cover - network/parse failure -> approved text
            return await self._fallback.explain(question, case, lang)
        return text or await self._fallback.explain(question, case, lang)

    @staticmethod
    def _prompt(question: str, case: CaseState, lang: str) -> str:
        return json.dumps(
            {
                "language": _LANGUAGE_NAME.get(lang, "Uzbek"),
                "question": question,
                "known_facts": case.known_facts(),
            },
            ensure_ascii=False,
        )


def build_openai_question_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> ExplainComplete:
    """Return an OpenAI-backed completion callable for question rephrasing."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 200,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "diagnostic_question",
                    "strict": True,
                    "schema": _QUESTION_JSON_SCHEMA,
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
