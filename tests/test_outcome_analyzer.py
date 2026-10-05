"""Outcome analyzer: classify a reply as success/failure/partial/unclear."""

from __future__ import annotations

import asyncio

from app.domain.case_state import CaseState, Outcome
from app.services.outcome_analyzer import (
    LLMOutcomeAnalyzer,
    OutcomeAnalysis,
    RuleOutcomeAnalyzer,
)


def _case() -> CaseState:
    return CaseState(case_id="c", session_id="s", domain="imei", resolution_card_id="imei-register")


def _run(analyzer: RuleOutcomeAnalyzer | LLMOutcomeAnalyzer, reply: str) -> OutcomeAnalysis:
    return asyncio.run(analyzer.analyze(reply, _case(), check=None, turn_id=1))


def test_rule_success() -> None:
    assert _run(RuleOutcomeAnalyzer(), "ishladi, rahmat").outcome is Outcome.SUCCESS


def test_rule_failure() -> None:
    assert _run(RuleOutcomeAnalyzer(), "hali ham shu xato chiqyapti").outcome is Outcome.FAILURE


def test_rule_partial_flags_new_problem() -> None:
    out = _run(RuleOutcomeAnalyzer(), "endi ochildi, lekin SMS kelmayapti")
    assert out.outcome is Outcome.PARTIAL
    assert out.new_problem_detected is True


def test_rule_dont_understand_is_unclear_not_failure() -> None:
    out = _run(RuleOutcomeAnalyzer(), "tushunmadim")
    assert out.outcome is Outcome.UNCLEAR


def test_rule_no_signal_is_unclear() -> None:
    assert _run(RuleOutcomeAnalyzer(), "qwerty").outcome is Outcome.UNCLEAR


def test_llm_uses_high_confidence_verdict() -> None:
    async def fake(prompt: str) -> str:
        return (
            '{"outcome": "success", "confidence": 0.9, "reason": "worked", '
            '"new_problem_detected": false, "facts": []}'
        )

    out = _run(LLMOutcomeAnalyzer(fake, fallback=RuleOutcomeAnalyzer()), "hammasi joyida")
    assert out.outcome is Outcome.SUCCESS and out.confidence == 0.9


def test_llm_low_confidence_falls_back_to_rules() -> None:
    async def shaky(prompt: str) -> str:
        return (
            '{"outcome": "success", "confidence": 0.2, "reason": "?", '
            '"new_problem_detected": false, "facts": []}'
        )

    # Rule analyzer sees a clear failure signal and overrides the shaky success.
    out = _run(LLMOutcomeAnalyzer(shaky, fallback=RuleOutcomeAnalyzer()), "ishlamadi yana xato")
    assert out.outcome is Outcome.FAILURE


def test_llm_error_falls_back_to_rules() -> None:
    async def broken(prompt: str) -> str:
        raise RuntimeError("network down")

    out = _run(LLMOutcomeAnalyzer(broken, fallback=RuleOutcomeAnalyzer()), "ishladi rahmat")
    assert out.outcome is Outcome.SUCCESS
