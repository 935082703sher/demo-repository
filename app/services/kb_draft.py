"""Turn a knowledge gap + an expert's answer into a structured KB draft.

The expert supplies the correct explanation in free text; this composes it into the
fields a good KB entry needs (title, problem, solution, verification, keywords,
synonyms...). The LLM only STRUCTURES the expert's content - it must not add facts the
expert did not give. A deterministic template is the fallback (and the mock/test
path): it keeps the expert's answer as the solution and derives keywords from the gap
so a later, similar question can retrieve the published article. The draft is always
reviewed by the expert before it can be approved.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.domain.knowledge_article import KnowledgeContent
from app.domain.knowledge_gap import KnowledgeGap
from app.services.assistant_voice import ASSISTANT_VOICE
from app.services.fact_extraction import _normalize


def _keywords_from_gap(gap: KnowledgeGap) -> list[str]:
    """Distinct meaningful tokens from the gap's questions, for retrieval."""
    seen: list[str] = []
    for text in [gap.normalized_question, *(_normalize(q) for q in gap.example_questions)]:
        for token in text.split():
            if len(token) > 2 and token not in seen:
                seen.append(token)
    return seen


class KbDraftComposer(Protocol):
    """Compose a structured KB draft from a gap and the expert's answer."""

    async def compose(self, gap: KnowledgeGap, expert_answer: str) -> KnowledgeContent: ...


class TemplateKbDraft:
    """Deterministic draft: expert answer as the solution, keywords from the gap."""

    async def compose(self, gap: KnowledgeGap, expert_answer: str) -> KnowledgeContent:
        title = (gap.question or gap.normalized_question or "Bilim maqolasi").strip()
        return KnowledgeContent(
            title=title[:120],
            domain=gap.domain,
            intent=gap.intent,
            problem=gap.question,
            solution=expert_answer.strip(),
            keywords=_keywords_from_gap(gap),
            synonyms=list(gap.example_questions),
        )


ComposeComplete = Callable[[str], Awaitable[str]]

_LLM_INSTRUCTIONS = (
    ASSISTANT_VOICE + " "
    "An expert has answered a question the knowledge base could not. Turn the expert's "
    "answer into a structured knowledge-base entry in the same language. Use ONLY the "
    "expert's content and the question - do NOT add facts, steps, figures or legal "
    "references the expert did not give. Fill the fields you can; leave others empty. "
    'Respond as JSON: {"title","problem","diagnosis","solution","verification",'
    '"when_to_route_operator","keywords":[],"synonyms":[]}.'
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "problem": {"type": "string"},
        "diagnosis": {"type": "string"},
        "solution": {"type": "string"},
        "verification": {"type": "string"},
        "when_to_route_operator": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "synonyms": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "problem",
        "diagnosis",
        "solution",
        "verification",
        "when_to_route_operator",
        "keywords",
        "synonyms",
    ],
    "additionalProperties": False,
}


class LLMKbDraft:
    """Structure the expert's answer via an LLM, with the template as a safety net."""

    def __init__(self, complete: ComposeComplete, fallback: KbDraftComposer) -> None:
        self._complete = complete
        self._fallback = fallback

    async def compose(self, gap: KnowledgeGap, expert_answer: str) -> KnowledgeContent:
        prompt = json.dumps(
            {
                "question": gap.question,
                "example_questions": gap.example_questions,
                "domain": gap.domain,
                "expert_answer": expert_answer,
            },
            ensure_ascii=False,
        )
        try:
            raw = json.loads(await self._complete(prompt))
            solution = str(raw.get("solution", "")).strip()
            if not solution:
                return await self._fallback.compose(gap, expert_answer)
            # Keep the gap's tokens in keywords so retrieval still finds it.
            keywords = list(dict.fromkeys([*raw.get("keywords", []), *_keywords_from_gap(gap)]))
            return KnowledgeContent(
                title=str(raw.get("title") or gap.question)[:120],
                domain=gap.domain,
                intent=gap.intent,
                problem=str(raw.get("problem", gap.question)),
                diagnosis=str(raw.get("diagnosis", "")),
                solution=solution,
                verification=str(raw.get("verification", "")),
                when_to_route_operator=str(raw.get("when_to_route_operator", "")),
                keywords=keywords,
                synonyms=list(raw.get("synonyms", []) or gap.example_questions),
            )
        except Exception:  # pragma: no cover - network/parse failure -> template
            return await self._fallback.compose(gap, expert_answer)


def build_openai_kb_draft_complete(
    *, api_key: str, model: str, timeout_seconds: float = 20.0
) -> ComposeComplete:
    """Return an OpenAI-backed completion callable for KB-draft composition."""
    import httpx

    async def complete(prompt: str) -> str:
        payload = {
            "model": model,
            "store": False,
            "instructions": _LLM_INSTRUCTIONS,
            "input": prompt,
            "max_output_tokens": 700,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "kb_draft",
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
            envelope = response.json()
            for output in envelope.get("output", []):
                for content in output.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        return str(content["text"])
            raise ValueError("no output_text")

    return complete
