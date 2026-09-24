"""Combined turn analyzer: one call returns route + facts, with rule fallback."""

from __future__ import annotations

import asyncio
import json

from app.domain.case_state import CaseState
from app.services.router import Route
from app.services.turn_analysis import LLMTurnAnalyzer, RuleTurnAnalyzer

_DUBAI = (
    "Dubaydan telefon olib kelgandim, ikkinchi sim ishlamay qoldi, IMEI SMS keldi."
)


def _case() -> CaseState:
    return CaseState(case_id="c", session_id="s", domain="imei")


def _run(analyzer: RuleTurnAnalyzer | LLMTurnAnalyzer, message: str):
    return asyncio.run(analyzer.analyze(message, _case(), turn_id=1))


def test_rule_analyzer_returns_route_and_facts() -> None:
    out = _run(RuleTurnAnalyzer(), _DUBAI)
    assert out.route is Route.CASE
    assert {f.name: f.value for f in out.facts}["device_origin"] == "imported"


def test_rule_analyzer_routes_a_question_to_rag() -> None:
    out = _run(RuleTurnAnalyzer(), "IMEI ro'yxatdan o'tkazish qancha turadi?")
    assert out.route is Route.RAG


def test_llm_analyzer_merges_facts_and_uses_llm_route() -> None:
    async def fake(prompt: str) -> str:
        return json.dumps(
            {
                "route": "rag",
                "facts": [
                    # Rules already know device_origin=imported; the LLM guess must lose.
                    {"name": "device_origin", "value": "local", "status": "inferred",
                     "confidence": 0.6},
                    # A fact the rules missed is added.
                    {"name": "declaration_status", "value": "not_declared",
                     "status": "explicit", "confidence": 0.9},
                ],
            }
        )

    out = _run(LLMTurnAnalyzer(fake, fallback=RuleTurnAnalyzer()), _DUBAI)
    facts = {f.name: f for f in out.facts}
    assert out.route is Route.RAG  # LLM route honoured
    assert facts["device_origin"].value == "imported"  # rule match kept
    assert facts["declaration_status"].value == "not_declared"  # LLM added


def test_llm_analyzer_falls_back_to_rules_on_error() -> None:
    async def broken(prompt: str) -> str:
        raise RuntimeError("network down")

    out = _run(LLMTurnAnalyzer(broken, fallback=RuleTurnAnalyzer()), _DUBAI)
    assert out.route is Route.CASE  # rule router
    assert "device_origin" in {f.name for f in out.facts}  # rule facts


def test_llm_analyzer_falls_back_to_rule_route_on_invalid_route() -> None:
    async def junk(prompt: str) -> str:
        return json.dumps({"route": "banana", "facts": []})

    out = _run(LLMTurnAnalyzer(junk, fallback=RuleTurnAnalyzer()), "telefonim bloklandi")
    assert out.route is Route.CASE  # rule router decided
