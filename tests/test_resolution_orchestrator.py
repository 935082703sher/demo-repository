"""Resolution orchestrator: offer -> outcome -> alternative / 1170 lifecycle."""

from __future__ import annotations

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus, Outcome
from app.domain.diagnostics import (
    DecisionTree,
    DiagnosticBundle,
    DiagnosticNode,
    DiagnosticOption,
    LocalizedText,
    OutcomeBranch,
    ResolutionCard,
    SuccessCheck,
)
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.outcome_analyzer import OutcomeAnalysis
from app.services.resolution_orchestrator import ResolutionOrchestrator


def _lt(text: str) -> LocalizedText:
    return LocalizedText(uz=text, ru=text)


def _card(
    card_id: str,
    cause: str,
    *,
    on_failure: OutcomeBranch | None = None,
    on_partial: OutcomeBranch | None = None,
    request_evidence: bool = False,
    lifecycle: bool = True,
) -> ResolutionCard:
    return ResolutionCard(
        id=card_id,
        title=_lt(card_id),
        probable_cause=_lt(f"cause {cause}"),
        steps=[_lt("do the step")],
        cause_key=cause,
        success_check=SuccessCheck(question=_lt("Ishladimi?")) if lifecycle else None,
        on_failure=on_failure,
        on_partial=on_partial,
        request_evidence=request_evidence,
    )


def _engine(cards: list[ResolutionCard]) -> DiagnosticEngine:
    options = [DiagnosticOption(value=c.id, label=_lt(c.id), card=c.id) for c in cards]
    tree = DecisionTree(
        id="t",
        domain="imei",
        case_type="x",
        title=_lt("t"),
        root="n1",
        nodes=[DiagnosticNode(id="n1", question=_lt("q"), options=options)],
    )
    return DiagnosticEngine(DiagnosticBundle(trees=[tree], cards=cards))


def _case() -> CaseState:
    return CaseState(case_id="c", session_id="s", domain="imei", active_tree="t")


def _out(outcome: Outcome, **kw: object) -> OutcomeAnalysis:
    return OutcomeAnalysis(outcome=outcome, confidence=0.9, **kw)  # type: ignore[arg-type]


def test_offer_marks_waiting_and_records_card() -> None:
    card = _card("c_a", "a")
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    d = orch.offer_card(case, card)
    assert d.kind == "offer_card" and case.status is CaseStatus.WAITING_FOR_RESULT
    assert case.card_tried("c_a") and case.resolution_card_id == "c_a"


def test_success_resolves() -> None:
    card = _card("c_a", "a")
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.SUCCESS))
    assert d.kind == "resolved" and case.status is CaseStatus.RESOLVED


def test_failure_offers_alternative_and_excludes_cause() -> None:
    alt = _card("c_b", "b")
    card = _card("c_a", "a", on_failure=OutcomeBranch(next_card="c_b"))
    orch = ResolutionOrchestrator(_engine([card, alt]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.FAILURE))
    assert d.kind == "offer_card" and d.card is not None and d.card.id == "c_b"
    assert case.status is CaseStatus.TRYING_ALTERNATIVE
    assert "a" in case.excluded_causes


def test_failed_card_is_not_repeated() -> None:
    card = _card("c_a", "a", on_failure=OutcomeBranch(next_card="c_a"))  # points back to itself
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.FAILURE))
    # c_a already tried, no other card -> must not re-offer it; exhausted -> 1170.
    assert d.kind == "call_1170" and case.status is CaseStatus.CALL_1170_RECOMMENDED


def test_partial_continues_at_node() -> None:
    card = _card("c_a", "a", on_partial=OutcomeBranch(next_node="n1"))
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.PARTIAL))
    assert d.kind == "ask_node" and d.node is not None and d.node.id == "n1"
    assert case.status is CaseStatus.DIAGNOSING


def test_unclear_reexplains_and_keeps_card() -> None:
    card = _card("c_a", "a")
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.UNCLEAR))
    assert d.kind == "reexplain" and case.resolution_card_id == "c_a"
    assert case.explanation.confusion_count == 1
    assert case.status is CaseStatus.WAITING_FOR_RESULT  # not discarded


def test_unclear_with_request_evidence_asks_for_error_text() -> None:
    card = _card("c_a", "a", request_evidence=True)
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.UNCLEAR))
    assert d.kind == "request_evidence"


def test_exhaustion_recommends_1170() -> None:
    card = _card("c_a", "a")  # no branch, no other card
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.FAILURE))
    assert d.kind == "call_1170"
    assert case.status is CaseStatus.CALL_1170_RECOMMENDED
    assert case.call_1170_reason == "all_safe_paths_exhausted"


def test_on_failure_status_call_1170_skips_auto_search() -> None:
    other = _card("c_b", "b")  # an untried sibling exists in the tree
    card = _card("c_a", "a", on_failure=OutcomeBranch(status="call_1170"))
    orch = ResolutionOrchestrator(_engine([card, other]))
    case = _case()
    orch.offer_card(case, card)
    d = orch.advance(case, _out(Outcome.FAILURE))
    assert d.kind == "call_1170" and case.status is CaseStatus.CALL_1170_RECOMMENDED
    assert not case.card_tried("c_b")  # the unrelated sibling is never offered


def test_failure_records_new_facts_in_attempt() -> None:
    card = _card("c_a", "a")
    orch = ResolutionOrchestrator(_engine([card]))
    case = _case()
    orch.offer_card(case, card)
    fact = Fact(name="error_code", value="E13", status=FactStatus.EXPLICIT)
    orch.advance(case, _out(Outcome.FAILURE, extracted_facts=[fact]))
    assert case.attempts[-1].new_facts == ["error_code"]
