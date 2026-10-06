"""The policy answer is composed from matched rules and stays legally grounded.

A composition may rephrase freely, but it must cite only clauses the evidence
supplied and must not alter a payment figure; otherwise the deterministic,
clause-cited summary is returned.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from app.domain.tariffs import TariffConfig
from app.services.policy_answer import (
    LLMPolicyAnswer,
    TemplatePolicyAnswer,
    build_policy_summary,
    introduces_no_new_number,
    is_legally_grounded,
)
from app.services.policy_matcher import PolicyMatch, PolicyMatcher
from tests.test_policy_matcher import _case

_RULES = Path("app/data/policy_rules.json")
_TARIFFS = Path("app/data/tariffs.json")


def _match_nonresident() -> PolicyMatch:
    matcher = PolicyMatcher.from_json(_RULES)
    return matcher.match(_case(), "Men xorijiy fuqaroman", when=date(2026, 1, 1))


# --- legal grounding gate ---


def test_grounding_accepts_cited_clauses_present_in_evidence() -> None:
    assert is_legally_grounded("Bu 6-band va 2-bandga asosan.", ["6", "2"]) is True


def test_grounding_rejects_an_invented_clause() -> None:
    assert is_legally_grounded("Bu 24-moddaga asosan.", ["6", "2"]) is False


def test_grounding_handles_sub_clause_numbers() -> None:
    assert is_legally_grounded("Chakana sotuvchi 6-1 band bo'yicha javobgar.", ["6-1"]) is True
    assert is_legally_grounded("Bu 10-1 bandga asosan.", ["6-1"]) is False


# --- numeric grounding: approved constants and clause citations are not "new numbers" ---


def test_number_check_allows_approved_constants() -> None:
    # *#06# and 1170 are published safe references, not facts; they may appear freely.
    assert introduces_no_new_number(
        "IMEI holatini tekshiring.", "*#06# ni tering, 1170 ga qo'ng'iroq qiling."
    )


def test_number_check_ignores_clause_citations() -> None:
    # Citing "28-band" is governed by the legal-grounding check, not the number check.
    assert introduces_no_new_number("Xorijiy fuqaro kanallari.", "Bu 28-band va 2-bandga asosan.")


def test_number_check_still_rejects_a_hallucinated_deadline() -> None:
    assert not introduces_no_new_number("30 kalendar kun ichida.", "90 kun ichida (28-band).")


# --- composer behaviour ---


def test_template_composer_returns_grounded_summary() -> None:
    match = _match_nonresident()
    summary = build_policy_summary(match, [], "uz", "https://lex.uz/docs/-4517458")
    out = asyncio.run(TemplatePolicyAnswer().compose(match, [], "uz", "msg", summary))
    assert out == summary
    assert "60 kalendar kun" in out  # the non-resident window is stated
    assert "lex.uz" in out  # with its source


def test_llm_composer_uses_a_grounded_composition() -> None:
    match = _match_nonresident()
    summary = build_policy_summary(match, [], "uz", "https://lex.uz/docs/-4517458")

    async def complete(_prompt: str) -> str:
        return (
            '{"answer": "Siz norezident bo\'lganingiz uchun qurilmangiz bir yil ichida '
            "60 kalendar kun ishlaydi (VMQ-778 2-band), keyin ro'yxatdan o'tkazish "
            'kerak."}'
        )

    out = asyncio.run(LLMPolicyAnswer(complete).compose(match, [], "uz", "msg", summary))
    assert "norezident" in out and "60 kalendar kun" in out and out != summary


def test_llm_composer_falls_back_on_invented_clause() -> None:
    match = _match_nonresident()
    summary = build_policy_summary(match, [], "uz", "https://lex.uz/docs/-4517458")

    async def complete(_prompt: str) -> str:
        return '{"answer": "Bu 44-moddaga asosan 90 kun ishlaydi."}'  # invented clause + figure

    out = asyncio.run(LLMPolicyAnswer(complete).compose(match, [], "uz", "msg", summary))
    assert out == summary  # ungrounded -> deterministic summary


def test_llm_composer_falls_back_on_altered_payment() -> None:
    matcher = PolicyMatcher.from_json(_RULES)
    tariffs = TariffConfig.from_json(_TARIFFS)
    match = matcher.match(
        _case(device_origin="imported"),
        "o'zim olib keldim, 30 kun ichida ro'yxatdan o'tkazaman",
        when=date(2026, 1, 1),
    )
    payment = tariffs.resolve("physical_person_within_30_days", date(2026, 1, 1))
    assert payment is not None
    summary = build_policy_summary(match, [payment], "uz", "https://lex.uz/docs/-4517458")

    async def complete(_prompt: str) -> str:
        return '{"answer": "To\'lov 90 000 so\'m (6-ilova)."}'  # altered the fee

    out = asyncio.run(LLMPolicyAnswer(complete).compose(match, [payment], "uz", "msg", summary))
    assert out == summary
