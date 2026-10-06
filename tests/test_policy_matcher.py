"""The policy matcher selects the VMQ-778 rules that fit a situation (UZ + RU).

These are the semantic regression tests: the law is used to pick the right clause
for the customer's situation - local purchase vs personal import, resident vs
non-resident, multi-IMEI, clone - not as a single generic answer.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from app.domain.case_state import CaseState, Fact, FactStatus
from app.services.policy_matcher import PolicyMatcher, derive_signals

_RULES = Path("app/data/policy_rules.json")


def _matcher() -> PolicyMatcher:
    return PolicyMatcher.from_json(_RULES)


def _case(**facts: str) -> CaseState:
    case = CaseState(case_id="c", session_id="s", domain="imei")
    for name, value in facts.items():
        case.upsert(Fact(name=name, value=value, status=FactStatus.EXPLICIT))
    return case


def _ids(matcher: PolicyMatcher, case: CaseState, message: str) -> set[str]:
    return {r.rule_id for r in matcher.match(case, message, when=date(2026, 1, 1)).rules}


# --- situation routing ---


def test_local_purchase_selects_seller_responsibility_not_personal_import() -> None:
    ids = _ids(_matcher(), _case(device_origin="local"), "Telefonni O'zbekistonda do'kondan oldim")
    assert "retail_seller_registration_responsibility" in ids
    assert "personal_import_registration" not in ids


def test_personal_import_by_resident_selects_import_rule() -> None:
    ids = _ids(_matcher(), _case(device_origin="imported"), "O'zim Dubaydan olib keldim")
    assert "personal_import_registration" in ids
    assert "retail_seller_registration_responsibility" not in ids


def test_nonresident_selects_60_day_window_not_resident_deadline() -> None:
    ids = _ids(_matcher(), _case(), "Men xorijiy fuqaroman, vaqtincha kelganman")
    assert "nonresident_registration_window_60_days" in ids
    assert "resident_registration_deadline_30_days" not in ids


def test_russian_nonresident_phrasing_is_understood() -> None:
    ids = _ids(_matcher(), _case(), "Я нерезидент, приехал на время")
    assert "nonresident_registration_window_60_days" in ids


def test_second_imei_selects_per_imei_payment() -> None:
    ids = _ids(_matcher(), _case(), "eSIM ulagach ikkinchi IMEI uchun to'lov chiqdi")
    assert "per_imei_separate_payment" in ids


def test_second_imei_from_fact_selects_per_imei_payment() -> None:
    ids = _ids(_matcher(), _case(affected_sim="second"), "ikkinchi raqam ishlamayapti")
    assert "per_imei_separate_payment" in ids


def test_clone_selects_not_registered_rule() -> None:
    ids = _ids(_matcher(), _case(), "IMEI klonlangan deb chiqyapti")
    assert "clone_or_undetermined_not_registered" in ids


def test_commercial_importer_overrides_personal_import() -> None:
    case = _case(device_origin="imported")
    signals = derive_signals(case, "Biz import qiluvchimiz, IM-40 rejimida partiya olib keldik")
    assert "imported_by_commercial_importer" in signals
    assert "personal_import" not in signals  # the stronger signal wins
    ids = {
        r.rule_id
        for r in _matcher()
        .match(case, "import qiluvchi IM-40 partiya", when=date(2026, 1, 1))
        .rules
    }
    assert "commercial_importer_registration_im40" in ids


def test_diplomatic_selects_special_order() -> None:
    ids = _ids(_matcher(), _case(), "Elchixona uchun qurilma ro'yxatga olmoqchimiz")
    assert "diplomatic_mission_special_order" in ids


# --- payment timing ---


def test_within_30_days_selects_20_percent_rule() -> None:
    ids = _ids(_matcher(), _case(), "Yangi oldim, 30 kun ichida ro'yxatdan o'tkazmoqchiman")
    assert "payment_physical_person_within_30_days" in ids
    assert "payment_physical_person_after_30_days" not in ids


def test_after_30_days_selects_25_percent_rule() -> None:
    ids = _ids(_matcher(), _case(), "Muddati o'tib ketgan, 30 kundan keyin ro'yxatdan o'tkazyapman")
    assert "payment_physical_person_after_30_days" in ids


# --- ordering, effectiveness, abstention ---


def test_more_specific_rule_ranks_first() -> None:
    match = _matcher().match(_case(device_origin="local"), "do'kondan oldim", when=date(2026, 1, 1))
    assert match.rules  # the situation-specific seller rule outranks the general requirement
    assert match.rules[0].specificity() >= match.rules[-1].specificity()


def test_rules_not_yet_effective_are_excluded() -> None:
    match = _matcher().match(_case(device_origin="local"), "do'kondan oldim", when=date(2018, 1, 1))
    assert match.rules == []  # VMQ-778 was not yet in force in 2018


def test_general_requirement_applies_without_specific_signals() -> None:
    ids = _ids(_matcher(), _case(), "Telefonimni ro'yxatdan o'tkazishim kerakmi?")
    assert "mandatory_registration_requirement" in ids
