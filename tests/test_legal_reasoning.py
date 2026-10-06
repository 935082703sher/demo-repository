"""The reasoning engine turns a situation into a clause-grounded plan, generally.

No per-question branches: the same engine handles any message, cites the clauses it
used, prefers specific over general, and abstains (no grounds) on an off-topic one.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.domain.case_state import CaseState, Fact, FactStatus
from app.domain.legal_clauses import ClauseBundle
from app.domain.tariffs import TariffConfig
from app.services.clause_retriever import ClauseRetriever
from app.services.legal_reasoning import LegalReasoningEngine
from app.services.policy_matcher import PolicyMatcher


def _engine() -> LegalReasoningEngine:
    return LegalReasoningEngine(
        ClauseRetriever(ClauseBundle.from_json(Path("app/data/vmq778_clauses.json"))),
        PolicyMatcher.from_json(Path("app/data/policy_rules.json")),
        TariffConfig.from_json(Path("app/data/tariffs.json")),
    )


def _case(**facts: str) -> CaseState:
    case = CaseState(case_id="c", session_id="s", domain="imei")
    for name, value in facts.items():
        case.upsert(Fact(name=name, value=value, status=FactStatus.EXPLICIT))
    return case


def test_complex_case_synthesises_several_clauses() -> None:
    # Local purchase + second IMEI: seller responsibility, per-IMEI payment, re-reg.
    r = _engine().reason(
        _case(device_origin="local", affected_sim="second"),
        "do'kondan oldim, eSIM ulagach ikkinchi IMEI uchun to'lov chiqdi",
        when=date(2026, 1, 1),
    )
    assert r.has_grounds()
    assert "6-1" in r.legal_basis  # retail-seller responsibility
    assert "44" in r.legal_basis  # per-IMEI payment
    assert len(r.legal_basis) >= 2  # a plan from several clauses, not one


def test_specific_clause_outranks_general() -> None:
    r = _engine().reason(_case(device_origin="local"), "do'kondan telefon sotib oldim")
    # The specific retail-seller sub-clause leads the general registration clause.
    assert r.legal_basis[0] == "6-1"


def test_payment_is_resolved_from_tariff_not_hardcoded() -> None:
    r = _engine().reason(
        _case(device_origin="imported"),
        "o'zim olib keldim, 30 kun ichida ro'yxatdan o'tkazaman",
        when=date(2026, 1, 1),
    )
    assert any(p.amount == 82_400 for p in r.payments)  # 20% of BHM, computed


def test_offtopic_message_has_no_grounds() -> None:
    r = _engine().reason(_case(), "bugun ob-havo qanday")
    assert not r.has_grounds()


def test_case_facts_expose_signals_and_known_facts() -> None:
    facts = _engine().case_facts(_case(device_origin="imported"), "men xorijiy fuqaroman")
    assert "user_is_nonresident" in facts.signals
    assert facts.known_facts.get("device_origin") == "imported"
