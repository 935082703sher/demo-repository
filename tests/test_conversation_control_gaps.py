"""Spec gaps closed on top of intent control: §22 RAG applicability, §24 summary, §26 gate."""

from __future__ import annotations

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus
from app.services.response_quality import (
    CAPABILITY_CLAIM,
    UNNECESSARY_MENU,
    check_reply,
)

# --- §26 response-quality gate -------------------------------------------------------


def test_gate_flags_a_live_check_claim() -> None:
    issues = check_reply(
        "Arizangizni tekshirdim, hammasi joyida.",
        option_values=[],
        done=True,
        current_intent=None,
    )
    assert CAPABILITY_CLAIM in issues


def test_gate_passes_an_honest_capability_limit() -> None:
    # "I can't check" is the opposite of claiming a lookup - it must not be flagged.
    issues = check_reply(
        "Men UZIMEI to'lov tizimiga kira olmayman va chekni o'zim chiqarib bera olmayman.",
        option_values=[],
        done=True,
        current_intent="payment_receipt_request",
    )
    assert issues == []


def test_gate_flags_a_menu_when_the_goal_is_already_known() -> None:
    issues = check_reply(
        "Mavzuni tanlang:",
        option_values=["imei-register", "mnp-port"],
        done=False,
        current_intent="registration_fee_question",
    )
    assert UNNECESSARY_MENU in issues


def test_gate_does_not_flag_outcome_buttons_as_a_menu() -> None:
    # Result buttons ("outcome:success") are not a topic menu, even mid-intent.
    issues = check_reply(
        "Hal bo'ldimi?",
        option_values=["outcome:success", "outcome:failure"],
        done=False,
        current_intent="registration_fee_question",
    )
    assert UNNECESSARY_MENU not in issues


# --- §24 conversation summary --------------------------------------------------------


def _case() -> CaseState:
    return CaseState(case_id="c1", session_id="s1")


def test_summary_is_pii_safe_and_captures_state() -> None:
    from app.api.routes.case import _build_conversation_summary

    case = _case()
    case.domain = "imei"
    case.current_intent = "registration_fee_question"
    case.status = CaseStatus.DIAGNOSING
    case.last_question = "intent:registration_fee:device_origin"
    case.upsert(
        Fact(name="device_origin", value="imported", status=FactStatus.EXPLICIT, source="user")
    )
    # A long, free-form value must be reduced to its fact name (no raw text leaks).
    case.upsert(
        Fact(
            name="note",
            value="a very long free form value that should not be inlined at all",
            status=FactStatus.EXPLICIT,
            source="user",
        )
    )
    summary = _build_conversation_summary(case)
    assert "goal=registration_fee_question" in summary
    assert "domain=imei" in summary
    assert "device_origin=imported" in summary
    assert "open_q=intent:registration_fee:device_origin" in summary
    # the long value is NOT present; only its name is
    assert "free form value" not in summary
    assert "note" in summary


# --- §22 RAG applicability -----------------------------------------------------------


class _Hit:
    def __init__(self, score: float) -> None:
        self.score = score


def test_applicability_keeps_the_best_and_drops_far_weaker_passages() -> None:
    from app.api.routes.case import _applicable_results

    results = [_Hit(10.0), _Hit(6.0), _Hit(3.0), _Hit(1.0)]
    kept = _applicable_results(results)
    # floor = 10.0 * 0.5 = 5.0: the best hit and the 6.0 passage stay; the weak tail goes.
    assert [h.score for h in kept] == [10.0, 6.0]


def test_applicability_never_drops_the_only_hit() -> None:
    from app.api.routes.case import _applicable_results

    assert len(_applicable_results([_Hit(4.2)])) == 1
    assert _applicable_results([]) == []
