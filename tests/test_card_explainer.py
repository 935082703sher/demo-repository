"""Resolution-card explainer (BLOK 4): natural cause, grounded fallback."""

from __future__ import annotations

import asyncio

from app.domain.case_state import CaseState
from app.services.card_explainer import LLMCardExplainer, TemplateCardExplainer

_CAUSE = "Bojsiz me'yordan ortiq qurilma uchun bojxona rasmiylashtiruvi talab qilinadi."


def _case() -> CaseState:
    return CaseState(case_id="c", session_id="s", domain="imei")


def _explain(explainer: LLMCardExplainer | TemplateCardExplainer, cause: str) -> str:
    return asyncio.run(explainer.explain(cause, _case(), "uz"))


def test_template_explainer_returns_cause_unchanged() -> None:
    assert _explain(TemplateCardExplainer(), _CAUSE) == _CAUSE


def test_llm_explainer_uses_the_model_text() -> None:
    async def fake(prompt: str) -> str:
        return '{"explanation": "Telefoningiz chetdan kelgani uchun bojxona kerak."}'

    out = _explain(LLMCardExplainer(fake, fallback=TemplateCardExplainer()), _CAUSE)
    assert out == "Telefoningiz chetdan kelgani uchun bojxona kerak."


def test_llm_explainer_falls_back_on_error() -> None:
    async def broken(prompt: str) -> str:
        raise RuntimeError("network down")

    out = _explain(LLMCardExplainer(broken, fallback=TemplateCardExplainer()), _CAUSE)
    assert out == _CAUSE  # approved wording is always available


def test_llm_explainer_falls_back_on_empty() -> None:
    async def empty(prompt: str) -> str:
        return '{"explanation": "   "}'

    out = _explain(LLMCardExplainer(empty, fallback=TemplateCardExplainer()), _CAUSE)
    assert out == _CAUSE
