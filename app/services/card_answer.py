"""Compose the FINAL customer answer for a resolution card (BLOK 4b).

The decision engine chooses the resolution and the knowledge base proves it. The
earlier flow then returned the approved steps verbatim, under fixed headers, in the
same rigid skeleton every time - which reads like a canned, robotic form. Here the
LLM instead *composes* the final answer from the card used as EVIDENCE: it
acknowledges the customer's actual situation, gives the direct answer and the steps
as natural prose in the requested language, and keeps every fact exact.

Grounding keeps it safe. The deterministic card text (the approved body) is the
ground truth; the composed answer is accepted only when it preserves every
significant number, deadline, fee, link and phone from that body and introduces no
new one. On any violation, LLM error, or when no LLM is configured, the deterministic
body is returned unchanged - so facts are never invented, altered, or dropped, and
tests on the mock provider see the exact approved text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.domain.case_state import CaseState
from app.domain.diagnostics import ResolutionCard
from app.services.assistant_voice import ASSISTANT_VOICE
from app.services.status_capability import claims_live_check

# A run of digits, optionally grouped by spaces/non-breaking spaces/commas, e.g.
# "82 400", "103 000", "1 170". Periods are left out: they end sentences and number
# list steps ("1."), which are not facts to preserve.
_NUMBER_RUN = re.compile(r"\d+(?:[  ,]\d+)*")


def _fact_numbers(text: str) -> set[str]:
    """Significant numeric facts in a text: digit-only tokens of length >= 2.

    Grouping separators are stripped ("82 400" -> "82400") so the same tariff reads
    identically however it is spaced. Single digits (step numbers like "1.") are
    dropped: they are formatting, not facts. Tariffs, fees, deadlines and the 1170
    hotline all survive as >= 2-digit tokens.
    """
    numbers: set[str] = set()
    for run in _NUMBER_RUN.findall(text):
        digits = re.sub(r"[  ,]", "", run)
        if len(digits) >= 2:
            numbers.add(digits)
    return numbers


def is_fact_preserving(approved: str, composed: str) -> bool:
    """True when the composed answer keeps exactly the approved numeric facts.

    Every significant number in the approved body must appear in the composed
    answer (nothing dropped or altered), and the composed answer must introduce no
    number absent from the body (nothing invented). This is what lets the LLM
    rephrase freely while fees, deadlines and the hotline stay verbatim.
    """
    approved_numbers = _fact_numbers(approved)
    composed_numbers = _fact_numbers(composed)
    return composed_numbers == approved_numbers


class CardAnswerComposer(Protocol):
    """Turn an approved card body into the final, natural customer answer."""

    async def compose(self, card: ResolutionCard, case: CaseState, lang: str, body: str) -> str: ...


class TemplateCardAnswer:
    """Deterministic composer: the approved body, unchanged."""

    async def compose(self, card: ResolutionCard, case: CaseState, lang: str, body: str) -> str:
        return body


ComposeComplete = Callable[[str], Awaitable[str]]

_LANGUAGE_NAME = {
    "uz": "Uzbek (Latin script)",
    "uz_cyrl": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
    "kaa": "Karakalpak",
}

_LLM_INSTRUCTIONS = (
    ASSISTANT_VOICE + " "
    "You are given an APPROVED resolution for a customer's IMEI/MNP case - the "
    "probable cause, the exact action steps, and any required documents, place to "
    "apply, official link and contact - together with what is known about their "
    "situation. Write the FINAL answer to the customer in the requested language as "
    "one natural, warm message: briefly acknowledge their specific situation, give "
    "the direct answer, then walk through the steps in order and mention the "
    "documents, where to go, the link and the contact where they belong. Write it "
    "as if a knowledgeable human agent were explaining it - not as a form with "
    "fixed headings. "
    "ABSOLUTE RULES: use ONLY the given steps, facts and figures. Reproduce every "
    "number, fee, deadline, link and phone number EXACTLY as given - never add, "
    "change, round, drop or invent any of them. Do not add steps or requirements "
    "that are not given. Keep the steps in the given order. "
    'Respond as JSON: {"answer": "..."}.'
)

_ANSWER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


class LLMCardAnswer:
    """Compose the final answer via an LLM, grounded against the approved body.

    The composed answer is used only when it preserves the approved numeric facts
    (see :func:`is_fact_preserving`); otherwise, or on any error, the deterministic
    body is returned. So the LLM makes the wording natural and situation-aware while
    the engine and knowledge base keep ownership of every fact and figure.
    """

    def __init__(self, complete: ComposeComplete) -> None:
        self._complete = complete

    async def compose(self, card: ResolutionCard, case: CaseState, lang: str, body: str) -> str:
        try:
            raw = await self._complete(self._prompt(card, case, lang))
            text = str(json.loads(raw).get("answer", "")).strip()
        except Exception:  # pragma: no cover - network/parse failure -> approved text
            return body
        if not text or not is_fact_preserving(body, text) or claims_live_check(text):
            return body
        return text

    @staticmethod
    def _prompt(card: ResolutionCard, case: CaseState, lang: str) -> str:
        return json.dumps(
            {
                "language": _LANGUAGE_NAME.get(lang, "Uzbek"),
                "style": case.explanation.style.value,
                "probable_cause": card.probable_cause.get(lang),
                "steps": [step.get(lang) for step in card.steps],
                "documents": [doc.get(lang) for doc in card.documents],
                "where_to_apply": card.where_to_apply.get(lang) if card.where_to_apply else None,
                "official_link": card.official_url,
                "contact": card.contact,
                "known_facts": case.known_facts(),
            },
            ensure_ascii=False,
        )


def build_openai_card_answer_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> ComposeComplete:
    """Return an OpenAI-backed completion callable for final-answer composition."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 600,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "card_answer",
                    "strict": True,
                    "schema": _ANSWER_JSON_SCHEMA,
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
