"""Resolution lifecycle domain models: attempts, exclusions, persistence."""

from __future__ import annotations

from app.domain.case_state import (
    CaseState,
    CaseStatus,
    ExplanationProfile,
    ExplanationStyle,
    Outcome,
    ResolutionAttempt,
)


def _case() -> CaseState:
    return CaseState(case_id="c1", session_id="s1", domain="imei")


def test_new_case_has_lifecycle_defaults() -> None:
    case = _case()
    assert case.status is CaseStatus.UNDERSTANDING
    assert case.tried_card_ids == [] and case.attempts == []
    assert case.explanation.style is ExplanationStyle.SIMPLE
    assert case.explanation.confusion_count == 0


def test_record_attempt_tracks_tried_cards_once() -> None:
    case = _case()
    case.record_attempt(ResolutionAttempt(card_id="imei-register", outcome=Outcome.FAILURE))
    case.record_attempt(ResolutionAttempt(card_id="imei-register", outcome=Outcome.FAILURE))
    assert case.card_tried("imei-register")
    assert case.tried_card_ids == ["imei-register"]  # de-duplicated
    assert len(case.attempts) == 2  # but every attempt is still logged


def test_exclude_cause_moves_it_out_of_remaining() -> None:
    case = _case()
    case.remaining_causes = ["payment_overdue", "clone_detected"]
    case.exclude_cause("payment_overdue")
    assert "payment_overdue" in case.excluded_causes
    assert case.remaining_causes == ["clone_detected"]


def test_lifecycle_state_survives_json_round_trip() -> None:
    case = _case()
    case.status = CaseStatus.WAITING_FOR_RESULT
    case.explanation = ExplanationProfile(style=ExplanationStyle.STEP_BY_STEP, confusion_count=2)
    case.record_attempt(ResolutionAttempt(card_id="imei-customs", outcome=Outcome.PARTIAL))
    case.call_1170_reason = "individual_review_required"

    restored = CaseState.model_validate_json(case.model_dump_json())
    assert restored.status is CaseStatus.WAITING_FOR_RESULT
    assert restored.explanation.style is ExplanationStyle.STEP_BY_STEP
    assert restored.explanation.confusion_count == 2
    assert restored.tried_card_ids == ["imei-customs"]
    assert restored.attempts[0].outcome is Outcome.PARTIAL
    assert restored.call_1170_reason == "individual_review_required"
