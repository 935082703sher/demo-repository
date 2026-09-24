"""Turn router (BLOK 3): rule decisions and LLM fallback."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.case_state import CaseState
from app.services.router import LLMRouter, Route, RuleRouter


def _case() -> CaseState:
    return CaseState(case_id="c", session_id="s")


def _decide(router: RuleRouter | LLMRouter, message: str) -> Route:
    return asyncio.run(router.decide(message, _case()))


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("salom", Route.GREETING),
        ("assalomu alaykum", Route.GREETING),
        ("rahmat", Route.GREETING),
        ("IMEI ro'yxatdan o'tkazish qancha turadi?", Route.RAG),
        ("MNP necha kun ichida amalga oshadi", Route.RAG),
        ("qanaqa hujjatlar kerak MNP uchun", Route.RAG),
        ("skolko stoit registratsiya imei", Route.RAG),
        ("IMEI ro'yxatdan o'tmayapti", Route.CASE),
        ("telefonim bloklandi", Route.CASE),
        ("raqamni ko'chirmoqchiman", Route.CASE),
        ("MNP arizam rad etildi, nega?", Route.CASE),
    ],
)
def test_rule_router_decisions(message: str, expected: Route) -> None:
    assert _decide(RuleRouter(), message) == expected


def test_rule_router_greeting_ignores_short_word_inside_other_words() -> None:
    # 'hi' must not match inside 'ko'chirmoqchiman'; it's a real transfer request.
    assert _decide(RuleRouter(), "raqamni ko'chirmoqchiman") == Route.CASE


def test_llm_router_uses_valid_decision() -> None:
    async def fake(prompt: str) -> str:
        return '{"route": "rag"}'

    router = LLMRouter(fake, fallback=RuleRouter())
    # A message the rules would call CASE, overridden by the LLM's valid RAG verdict.
    assert _decide(router, "telefonim bloklandi") == Route.RAG


def test_llm_router_falls_back_on_error() -> None:
    async def broken(prompt: str) -> str:
        raise RuntimeError("network down")

    router = LLMRouter(broken, fallback=RuleRouter())
    assert _decide(router, "telefonim bloklandi") == Route.CASE  # rule fallback


def test_llm_router_falls_back_on_invalid_route() -> None:
    async def junk(prompt: str) -> str:
        return '{"route": "banana"}'

    router = LLMRouter(junk, fallback=RuleRouter())
    assert _decide(router, "IMEI narxi qancha?") == Route.RAG  # rule fallback kept
