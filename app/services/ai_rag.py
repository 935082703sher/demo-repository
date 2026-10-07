"""Pure AI + RAG turn handler (the AI_RAG_ONLY configuration mode).

Every turn runs one flow: understand the customer's current goal from their message and
the conversation context, retrieve the relevant approved knowledge (the KB and the
VMQ-778 clauses), apply it to the situation, and either answer naturally or ask the one
question whose answer would change the reply. There is no decision tree, no menu or
buttons, no intent/keyword canned reply, no verbatim FAQ/card text, and no automatic
1170 fallback. The approved FAQ/card/clause text is used only as RETRIEVED EVIDENCE; it
is never emitted as the final answer.

The technical controls stay on:

- the answer is grounded - it may cite only the evidence supplied, and it may contain no
  fee, deadline or other number that is absent from that evidence (nothing invented);
- it may never claim a live-system lookup the assistant cannot make (capability honesty);
- a model failure, or no configured model, is reported openly - the handler never hides a
  failure behind canned text (there is no mock answer generator here).

This module owns only the LLM call and these checks; retrieval inputs are passed in.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.case_state import CaseState
from app.services.assistant_voice import ASSISTANT_VOICE
from app.services.grounding import GroundingValidator
from app.services.status_capability import claims_live_check

AiRagComplete = Callable[[str], Awaitable[str]]

# Numbers that are not situational facts, so they never count as "invented": the 1170
# hotline, the VMQ-778 number, the *#06# IMEI code, the +998 country code.
_SAFE_NUMBERS = frozenset({"1170", "778", "06", "998"})
_NUMBER_RUN = re.compile(r"\d+(?:[  ,]\d+)*")

_LANGUAGE_NAME = {
    "uz": "Uzbek (Latin script)",
    "uz_cyrl": "Uzbek (Cyrillic script)",
    "ru": "Russian",
    "en": "English",
    "kaa": "Karakalpak",
}

# An open, honest technical-error line (no hidden fallback to a canned answer).
_MODEL_ERROR = {
    "uz": "⚠️ Texnik xatolik: AI modeli hozir javob bera olmadi. Tayyor javobga "
    "o'tmayman — birozdan so'ng qayta urinib ko'ring.",
    "uz_cyrl": "⚠️ Техник хатолик: AI модели ҳозир жавоб бера олмади. Тайёр жавобга "
    "ўтмайман — бироздан сўнг қайта уриниб кўринг.",
    "ru": "⚠️ Техническая ошибка: модель ИИ сейчас не смогла ответить. Я не перехожу "
    "на готовый ответ — попробуйте ещё раз чуть позже.",
    "en": "⚠️ Technical error: the AI model could not answer right now. I won't fall back "
    "to a canned reply — please try again shortly.",
    "kaa": "⚠️ Texnikalıq qátelik: AI modeli házir juwap bere almadı. Tayar juwapqa "
    "ótpeymen — azıraqtan keyin qayta urınıp kóriń.",
}
# Honest limitation when the evidence does not support a grounded answer (no invention,
# and - per this mode - no automatic routing to the hotline).
_NO_GROUND = {
    "uz": "Bu savol bo'yicha tasdiqlangan manbalarimda aniq ma'lumot topa olmadim, "
    "shuning uchun taxmin qilmayman. Savolni biroz aniqroq yozsangiz, yana qidirib ko'raman.",
    "uz_cyrl": "Бу савол бўйича тасдиқланган манбаларимда аниқ маълумот топа олмадим, "
    "шунинг учун тахмин қилмайман. Саволни бироз аниқроқ ёзсангиз, яна қидириб кўраман.",
    "ru": "По этому вопросу я не нашёл точных данных в проверенных источниках и не буду "
    "домысливать. Уточните вопрос — я поищу ещё раз.",
    "en": "I couldn't find confirmed information for this in my sources, so I won't guess. "
    "If you rephrase the question a bit, I'll search again.",
    "kaa": "Bul soraw boyınsha tastıyıqlanǵan dereklerimde anıq maǵlıwmat taba almadım, "
    "sonlıqtan boljamayman. Sorawdı anıǵıraq jazsańız, qayta izleymen.",
}

_INSTRUCTIONS = (
    ASSISTANT_VOICE + " "
    "You are the RTMC assistant for IMEI device registration and MNP number porting. "
    "Work in ONE flow every turn: understand the customer's CURRENT goal from their latest "
    "message and the conversation context, then use ONLY the supplied EVIDENCE to answer. "
    "Handle a new topic, a correction, or an 'I didn't understand' naturally from the "
    "context: for 'I didn't understand', restate your previous answer (given as "
    "last_answer) in simpler words - do not repeat it verbatim and do not start over. "
    "open_request is the customer's request still being handled. If pending_question is "
    "set, you asked it last turn and customer_message is the answer to it: combine that "
    "answer with open_request and now actually answer open_request - never reply with a "
    "bare acknowledgement. A short message such as 'online', 'yes' or 'tell me now' "
    "continues open_request. If customer_message clearly starts a different topic, "
    "answer only the new topic and ignore last_answer. "
    "Write in the requested language as a natural, concise human reply - never a form with "
    "headings, never a menu or buttons. "
    "If one specific missing fact would change the answer, ask EXACTLY ONE short clarifying "
    "question (set type='question'); otherwise answer (type='answer'). "
    "ABSOLUTE RULES: use only the evidence for any fact, figure, deadline, procedure, "
    "contact, status or legal claim - never invent one, and reproduce every number exactly "
    "as in the evidence. If the evidence does not cover the question, say so openly and "
    "briefly instead of guessing; do not push a phone number. Never claim you checked, "
    "looked up, cancelled, registered or confirmed anything in a live system - you cannot "
    "access any system. State any assumption as an assumption. "
    "In used_sources list the ids of the evidence items you actually relied on (for an "
    "answer that states a fact this must be non-empty; for a greeting or a question it may "
    'be empty). Respond as JSON: {"type": "answer"|"question", "reply": "...", '
    '"used_sources": ["id", ...]}.'
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["answer", "question"]},
        "reply": {"type": "string"},
        "used_sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["type", "reply", "used_sources"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class Evidence:
    """One retrieved source item offered to the model (and allowed for citation)."""

    source_id: str
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class AiRagResult:
    """The outcome of one AI+RAG turn."""

    reply: str
    is_question: bool = False
    error: bool = False
    sources: list[tuple[str, str]] = field(default_factory=list)


def _numbers(text: str) -> set[str]:
    out: set[str] = set()
    for run in _NUMBER_RUN.findall(text):
        digits = re.sub(r"[  ,]", "", run)
        if len(digits) >= 2:
            out.add(digits)
    return out


class AiRagResponder:
    """Run one grounded, natural AI+RAG turn, or report an open technical error."""

    def __init__(
        self,
        complete: AiRagComplete | None,
        grounding: GroundingValidator,
        *,
        model_name: str = "",
    ) -> None:
        self._complete = complete
        self._grounding = grounding
        self._model_name = model_name

    @property
    def available(self) -> bool:
        """True when a real model is wired (no mock answer generator stands in)."""
        return self._complete is not None

    async def respond(
        self, case: CaseState, message: str, lang: str, evidence: list[Evidence]
    ) -> AiRagResult:
        """Understand, apply the evidence, and answer naturally - or surface an error."""
        if self._complete is None:
            return AiRagResult(reply=_pick(_MODEL_ERROR, lang), error=True)
        prompt = self._prompt(case, message, lang, evidence)
        try:
            raw = await self._complete(prompt)
            data = json.loads(raw)
        except Exception:
            return AiRagResult(reply=_pick(_MODEL_ERROR, lang), error=True)
        reply = str(data.get("reply", "")).strip()
        kind = str(data.get("type", "answer"))
        used = [str(s) for s in data.get("used_sources", []) if str(s)]
        if not reply or claims_live_check(reply):
            # Empty, or it claimed a live lookup it cannot make: do not ship it.
            return AiRagResult(reply=_pick(_MODEL_ERROR, lang), error=True)
        if kind == "question":
            return AiRagResult(reply=reply, is_question=True)
        allowed = {e.source_id for e in evidence}
        evidence_numbers = {n for e in evidence for n in _numbers(e.text)} | _SAFE_NUMBERS
        cites_only_supplied = all(src in allowed for src in used)
        no_invented_numbers = _numbers(reply) <= evidence_numbers
        if not cites_only_supplied or not no_invented_numbers:
            # A fabricated citation or an invented number: fall back to an open
            # limitation, never to canned domain text and never to the hotline.
            return AiRagResult(reply=_pick(_NO_GROUND, lang))
        sources = [(e.source_id, e.title) for e in evidence if e.source_id in set(used)]
        return AiRagResult(reply=reply, sources=sources)

    def _prompt(self, case: CaseState, message: str, lang: str, evidence: list[Evidence]) -> str:
        return json.dumps(
            {
                "language": _LANGUAGE_NAME.get(lang, "Uzbek (Latin script)"),
                "conversation_summary": case.conversation_summary,
                "known_facts": case.known_facts(),
                "last_answer": case.last_answer,
                "open_request": case.current_problem,
                "pending_question": case.last_question,
                "customer_message": message,
                "evidence": [
                    {"id": e.source_id, "title": e.title, "text": e.text} for e in evidence
                ],
            },
            ensure_ascii=False,
        )


def _pick(table: dict[str, str], lang: str) -> str:
    return table.get(lang) or table["uz"]


def build_openai_ai_rag_complete(
    *, api_key: str, model: str, timeout_seconds: float = 30.0, max_output_tokens: int = 700
) -> AiRagComplete:
    """Return an OpenAI-backed completion callable for the AI+RAG turn."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ai_rag_turn",
                    "strict": True,
                    "schema": _SCHEMA,
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
