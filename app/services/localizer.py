"""Translate short UI strings (menu titles, button labels) into a chosen language.

The decision trees and resolution cards ship their text in Uzbek and Russian only,
so a Karakalpak or Uzbek-Cyrillic user would otherwise see the navigation labels in
Uzbek. This localizer translates those short display strings on demand via an LLM,
with a deterministic fallback (the original text) on any failure.

It is used ONLY for display chrome that carries no RTMC facts - menu titles and
answer-button labels. It is never used on resolution-card steps, documents, tariffs,
deadlines or contacts: those approved facts stay verbatim so a number is never
rephrased. The instruction also tells the model to preserve any digit, code, URL or
phone number it does see, and a result whose item count or shape is wrong is dropped
in favour of the originals.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

_LANGUAGE_NAME = {
    "uz": "Uzbek (Latin script)",
    "uz_cyrl": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
    "kaa": "Karakalpak",
}


class Localizer(Protocol):
    """Translate a list of short UI strings into the requested language."""

    async def localize(self, texts: list[str], lang: str) -> list[str]: ...


class TemplateLocalizer:
    """Deterministic localizer: return the strings unchanged (the safety net)."""

    async def localize(self, texts: list[str], lang: str) -> list[str]:
        return list(texts)


LocalizeComplete = Callable[[str], Awaitable[str]]

_LLM_INSTRUCTIONS = (
    "You translate short UI strings (menu titles and answer-button labels) for an "
    "Uzbek telecom assistant into the requested language. Translate every item, "
    "keeping the SAME meaning, the SAME order and the SAME number of items. Keep any "
    "digit, number, short code, URL or phone number (e.g. 30, 1170, *1170#) exactly "
    "as given. Use short, natural, everyday words. Invent nothing. "
    'Respond as JSON: {"texts": ["..."]}.'
)

_LOCALIZE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"texts": {"type": "array", "items": {"type": "string"}}},
    "required": ["texts"],
    "additionalProperties": False,
}


class LLMLocalizer:
    """Translate UI strings via an LLM, with the template localizer as a safety net."""

    def __init__(self, complete: LocalizeComplete, fallback: Localizer) -> None:
        self._complete = complete
        self._fallback = fallback

    async def localize(self, texts: list[str], lang: str) -> list[str]:
        if not texts:
            return []
        try:
            raw = await self._complete(self._prompt(texts, lang))
            out = json.loads(raw).get("texts", [])
        except Exception:  # pragma: no cover - network/parse failure -> originals
            return await self._fallback.localize(texts, lang)
        if (
            not isinstance(out, list)
            or len(out) != len(texts)
            or not all(isinstance(item, str) and item.strip() for item in out)
        ):
            return await self._fallback.localize(texts, lang)
        return [item.strip() for item in out]

    @staticmethod
    def _prompt(texts: list[str], lang: str) -> str:
        return json.dumps(
            {"language": _LANGUAGE_NAME.get(lang, "Uzbek"), "texts": texts},
            ensure_ascii=False,
        )


def build_openai_localize_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> LocalizeComplete:
    """Return an OpenAI-backed completion callable for UI-string translation."""
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
                    "name": "localized_labels",
                    "strict": True,
                    "schema": _LOCALIZE_JSON_SCHEMA,
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
