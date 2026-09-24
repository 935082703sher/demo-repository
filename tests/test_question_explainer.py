"""Question explainer (BLOK 4, questions): natural question, grounded fallback."""

from __future__ import annotations

import asyncio

from app.domain.case_state import CaseState
from app.services.question_explainer import LLMQuestionExplainer, TemplateQuestionExplainer

_QUESTION = "Qurilmani qayerdan oldingiz?"


def _case() -> CaseState:
    return CaseState(case_id="c", session_id="s", domain="imei")


def _explain(explainer: LLMQuestionExplainer | TemplateQuestionExplainer, q: str) -> str:
    return asyncio.run(explainer.explain(q, _case(), "uz"))


def test_template_returns_question_unchanged() -> None:
    assert _explain(TemplateQuestionExplainer(), _QUESTION) == _QUESTION


def test_llm_uses_the_model_question() -> None:
    async def fake(prompt: str) -> str:
        return '{"question": "Telefoningizni qayerdan oldingiz?"}'

    out = _explain(LLMQuestionExplainer(fake, fallback=TemplateQuestionExplainer()), _QUESTION)
    assert out == "Telefoningizni qayerdan oldingiz?"


def test_llm_falls_back_on_error() -> None:
    async def broken(prompt: str) -> str:
        raise RuntimeError("network down")

    out = _explain(LLMQuestionExplainer(broken, fallback=TemplateQuestionExplainer()), _QUESTION)
    assert out == _QUESTION  # tree's own wording is always available


def test_llm_falls_back_on_empty() -> None:
    async def empty(prompt: str) -> str:
        return '{"question": "  "}'

    out = _explain(LLMQuestionExplainer(empty, fallback=TemplateQuestionExplainer()), _QUESTION)
    assert out == _QUESTION
