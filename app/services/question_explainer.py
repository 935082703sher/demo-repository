"""Rephrase a diagnostic question naturally (BLOK 4, questions).

The decision tree still decides WHICH question to ask and keeps its exact answer
options; this only makes the question text itself read warm and situation-aware
instead of like a fixed form field. The options (the buttons) are never touched,
so answer mapping is unaffected, and any LLM failure falls back to the tree's own
wording. It never invents facts or adds choices.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.domain.case_state import CaseState
from app.services.assistant_voice import ASSISTANT_VOICE

# A run of 7+ digits is likely personal data (IMEI, phone, passport): the model sees
# it only as its last 4 digits, so it can acknowledge "IMEI ...0302" without ever
# echoing the full number back.
_LONG_DIGITS = re.compile(r"\d[\d  -]{5,}\d")


def _mask_pii(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return f"…{digits[-4:]}" if len(digits) >= 7 else match.group(0)

    return _LONG_DIGITS.sub(repl, text)


class QuestionExplainer(Protocol):
    """Turn an approved question into a natural, situation-aware question."""

    async def explain(self, question: str, case: CaseState, lang: str) -> str: ...


class TemplateQuestionExplainer:
    """Deterministic explainer: the tree's own question text, unchanged."""

    async def explain(self, question: str, case: CaseState, lang: str) -> str:
        return question


ExplainComplete = Callable[[str], Awaitable[str]]

_LANGUAGE_NAME = {
    "uz": "Uzbek (Latin script)",
    "uz_cyrl": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
    "kaa": "Karakalpak",
}

_LLM_INSTRUCTIONS = (
    ASSISTANT_VOICE + " "
    "You are a warm, competent support agent gathering the ONE missing detail needed "
    "to help. You are given the customer's problem, what is already known, and the "
    "next diagnostic QUESTION to ask. Reply like a real person, in the requested "
    "language, in two or three short sentences: first briefly acknowledge their "
    "specific situation so they feel heard; if it helps, say in a few words why this "
    "detail decides the answer; then ask the given question in natural words. "
    "Rules: ask only this one question; do NOT list, add, remove or rename any answer "
    "option (the choices are shown as separate buttons); never re-ask what is already "
    "known; invent no facts; never repeat back full personal data - refer to an IMEI "
    'only by its last 4 digits. Respond as JSON: {"question": "..."}.'
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
        problem = case.original_problem or case.problem_summary or ""
        facts = {name: _mask_pii(str(value)) for name, value in case.known_facts().items()}
        return json.dumps(
            {
                "language": _LANGUAGE_NAME.get(lang, "Uzbek"),
                "problem": _mask_pii(problem),
                "question": question,
                "known_facts": facts,
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
            "max_output_tokens": 320,
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
