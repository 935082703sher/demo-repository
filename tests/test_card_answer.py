"""The final card answer is LLM-composed from evidence, but never invents a fact.

The approved card is the ground truth. The composer may rephrase it into a natural,
situation-aware message, yet every fee, deadline, link and phone must survive exactly
- otherwise the deterministic approved body is returned unchanged. The mock provider
(used by every other test and the evaluations) always gets that exact body.
"""

from __future__ import annotations

import asyncio

from app.domain.case_state import CaseState
from app.domain.diagnostics import LocalizedText, ResolutionCard
from app.services.card_answer import (
    LLMCardAnswer,
    TemplateCardAnswer,
    is_fact_preserving,
)


def _lt(text: str) -> LocalizedText:
    return LocalizedText(uz=text, ru=text)


def _card() -> ResolutionCard:
    return ResolutionCard(
        id="imei-register",
        title=_lt("Ro'yxatdan o'tkazish"),
        probable_cause=_lt("IMEI hali ro'yxatdan o'tmagan."),
        steps=[_lt("uzimei.uz saytiga kiring"), _lt("To'lovni amalga oshiring")],
        official_url="https://uzimei.uz",
        contact="1170",
    )


def _case() -> CaseState:
    return CaseState(case_id="c", session_id="s", domain="imei")


# --- grounding: the fact-preservation gate ---


def test_fact_preserving_accepts_a_faithful_rephrasing() -> None:
    approved = "To'lov 82 400 so'm. 30 kun ichida. 1170 ga qo'ng'iroq qiling."
    composed = (
        "Tushundim. To'lovingiz 82 400 so'm bo'ladi va buni 30 kun ichida amalga "
        "oshirishingiz kerak. Savol bo'lsa, 1170 raqamiga qo'ng'iroq qiling."
    )
    assert is_fact_preserving(approved, composed) is True


def test_fact_preserving_rejects_a_changed_tariff() -> None:
    approved = "To'lov 82 400 so'm."
    composed = "To'lovingiz 82 500 so'm bo'ladi."  # altered fee
    assert is_fact_preserving(approved, composed) is False


def test_fact_preserving_rejects_an_invented_number() -> None:
    approved = "uzimei.uz saytiga kiring va to'lovni amalga oshiring."
    composed = "uzimei.uz saytiga kiring. Bu odatda 14 kun davom etadi."  # invented "14 kun"
    assert is_fact_preserving(approved, composed) is False


def test_fact_preserving_rejects_a_dropped_deadline() -> None:
    approved = "30 kun ichida 1170 ga murojaat qiling."
    composed = "1170 ga murojaat qiling."  # dropped the 30-day deadline
    assert is_fact_preserving(approved, composed) is False


def test_spacing_variants_of_the_same_tariff_match() -> None:
    assert is_fact_preserving("To'lov 103 000 so'm.", "To'lov 103000 so'm.") is True
    assert is_fact_preserving("To'lov 103 000 so'm.", "To'lov 103,000 so'm.") is True


def test_step_numbers_are_formatting_not_facts() -> None:
    # Numbered steps on one side, prose bullets on the other: still fact-preserving.
    approved = "1. uzimei.uz ga kiring\n2. to'lovni amalga oshiring"
    composed = "Avval uzimei.uz saytiga kiring, so'ngra to'lovni amalga oshiring."
    assert is_fact_preserving(approved, composed) is True


# --- composer behaviour ---


def test_template_composer_returns_body_unchanged() -> None:
    body = "Approved body with the fee 82 400 and 1170."
    out = asyncio.run(TemplateCardAnswer().compose(_card(), _case(), "uz", body))
    assert out == body


def test_llm_composer_uses_a_faithful_composition() -> None:
    natural = (
        '{"answer": "Tushundim, IMEI hali ro\'yxatdan o\'tmagan. uzimei.uz saytiga '
        "kiring va to'lovni amalga oshiring. Havola: https://uzimei.uz, yordam: 1170.\"}"
    )

    async def complete(_prompt: str) -> str:
        return natural

    body = "IMEI hali ro'yxatdan o'tmagan.\n1. uzimei.uz saytiga kiring\nhttps://uzimei.uz\n1170"
    out = asyncio.run(LLMCardAnswer(complete).compose(_card(), _case(), "uz", body))
    assert "Tushundim" in out and out != body  # the natural wording was used


def test_llm_composer_falls_back_when_it_alters_a_fact() -> None:
    async def complete(_prompt: str) -> str:
        return '{"answer": "To\'lov 99 999 so\'m, 1170 ga murojaat qiling."}'  # invented fee

    body = "To'lov 82 400 so'm. 1170 ga murojaat qiling."
    out = asyncio.run(LLMCardAnswer(complete).compose(_card(), _case(), "uz", body))
    assert out == body  # ungrounded composition rejected -> approved body


def test_llm_composer_falls_back_on_provider_error() -> None:
    async def complete(_prompt: str) -> str:
        raise RuntimeError("network down")

    body = "To'lov 82 400 so'm."
    out = asyncio.run(LLMCardAnswer(complete).compose(_card(), _case(), "uz", body))
    assert out == body
