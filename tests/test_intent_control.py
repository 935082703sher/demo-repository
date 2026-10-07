"""Natural conversation & intent control: answer what the customer is asking NOW.

The current message's goal outranks earlier turns; a completed step is respected; a
question is asked only when it changes the next step, never twice, and never one that
is irrelevant to the goal (no "where did you buy the phone?" for a receipt request).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.intent_control import (
    PAYMENT_RECEIPT,
    REGISTRATION_FEE,
    detect_intent,
    fee_followup_reply,
    fee_reply,
    mentions_amount,
    receipt_reply,
    transaction_facts,
)
from app.services.status_capability import claims_live_check

_LANGS = ("uz", "uz_cyrl", "ru", "en", "kaa")
_RECEIPT_EN = (
    "On July 1, 2026, I registered two IMEI codes and paid UZS 164,800. Registration was "
    "successful, but I did not receive an electronic receipt. I need an official receipt "
    "for reimbursement."
)
_FEE_RU = (
    "Здравствуйте, я был в Узбекистане и купил сим карту... сумма регистрации "
    "2 620 786,6 сум. Это правда так дорого?"
)
# The irrelevant question the spec forbids for a receipt request, in every language.
_ORIGIN_QUESTION_MARKERS = ("qayerdan oldingiz", "where did you buy", "где вы купили")


# --- unit: what the message is about ---------------------------------------------


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        (_RECEIPT_EN, PAYMENT_RECEIPT),
        ("Elektron chekni qayerdan olaman?", PAYMENT_RECEIPT),
        ("To'lov qildim. Endi chek kerak.", PAYMENT_RECEIPT),
        ("Оплатил регистрацию, но электронный чек не пришёл", PAYMENT_RECEIPT),
        ("Registratsiya juda qimmat.", REGISTRATION_FEE),
        (_FEE_RU, REGISTRATION_FEE),
        ("Why is the registration so expensive?", REGISTRATION_FEE),
        # a receipt request wins over a fee complaint in the same message
        ("Qimmat bo'ldi, lekin hozir faqat to'lov cheki kerak", PAYMENT_RECEIPT),
    ],
)
def test_detects_the_current_explicit_goal(message: str, intent: str) -> None:
    assert detect_intent(message) == intent


@pytest.mark.parametrize(
    "message",
    [
        "Xarid cheki yo'q",  # a shop purchase receipt, not a payment receipt
        "IMEI qutida va chekda yozilgan",
        "IMEI ro'yxatdan o'tkazish qancha turadi?",  # a price question, not a complaint
        "Telefonim ro'yxatdan o'tmayapti",
    ],
)
def test_ordinary_messages_state_no_controlled_intent(message: str) -> None:
    assert detect_intent(message) is None


def test_completed_steps_are_extracted_as_facts() -> None:
    facts = {f.name: f.value for f in transaction_facts(_RECEIPT_EN, turn_id=1)}
    assert facts == {
        "registration_status": "success",
        "payment_status": "success",
        "receipt_status": "missing",
    }


def test_amount_detection() -> None:
    assert mentions_amount(_FEE_RU)
    assert mentions_amount("I paid UZS 164,800")
    assert not mentions_amount("Registratsiya juda qimmat")


@pytest.mark.parametrize("lang", _LANGS)
def test_replies_exist_and_never_claim_a_capability(lang: str) -> None:
    replies = [
        receipt_reply(lang, registration_succeeded=True),
        receipt_reply(lang, registration_succeeded=False),
        fee_reply(lang, amount_quoted=True, device_origin=None),
        fee_reply(lang, amount_quoted=False, device_origin="imported"),
        fee_followup_reply(lang, "imported"),
        fee_followup_reply(lang, "local"),
    ]
    for reply in replies:
        assert reply.strip()
        assert not claims_live_check(reply)


def test_fee_reply_asks_one_question_only_when_origin_is_unknown() -> None:
    assert fee_reply("en", amount_quoted=True, device_origin=None).count("?") == 1
    assert "?" not in fee_reply("en", amount_quoted=True, device_origin="imported")


# --- the conversation ---------------------------------------------------------------


def _post(client: TestClient, message: str, session: str, lang: str = "uz") -> dict[str, Any]:
    return dict(
        client.post(
            "/assistant/converse",
            json={"message": message, "session_id": session, "language": lang},
        ).json()
    )


def test_receipt_request_is_answered_directly_in_the_users_language() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, _RECEIPT_EN, "ic-1")
        gaps = client.portal.call(client.app.state.knowledge_gaps.list)  # type: ignore[attr-defined,union-attr]
    reply = body["reply"]
    assert reply.startswith("Understood.")  # English in, English out
    assert "isn't a registration problem" in reply  # the success is respected
    assert "can't access the UZIMEI payment system" in reply  # capability limit
    assert "application number" in reply  # what the customer can do
    assert body["options"] == []  # no menu
    assert not any(m in reply.lower() for m in _ORIGIN_QUESTION_MARKERS)
    assert body["done"] is True
    assert body["known_facts"]["registration_status"] == "success"
    assert body["known_facts"]["receipt_status"] == "missing"
    # No receipt procedure in the KB: a knowledge gap for expert review, not an invention.
    assert any(g.intent == PAYMENT_RECEIPT for g in gaps)


def test_fee_complaint_asks_one_natural_question_then_answers() -> None:
    with TestClient(create_app()) as client:
        first = _post(client, _FEE_RU, "ic-2", "ru")
        second = _post(client, "Привёз телефон из Дубая", "ic-2", "ru")
    assert "не могу проверить начисление напрямую" in first["reply"]
    assert first["reply"].count("?") == 1  # exactly one question
    assert first["options"] == []  # free text, not a button menu
    assert first["done"] is False
    assert "оператору системы UZIMEI" in second["reply"]
    assert second["done"] is True


def test_new_goal_replaces_the_old_flow() -> None:
    with TestClient(create_app()) as client:
        _post(client, "Registratsiya juda qimmat.", "ic-3")
        body = _post(
            client,
            "To'lov qildim, registratsiya muvaffaqiyatli bo'ldi. Endi elektron chek kerak.",
            "ic-3",
        )
    assert body["reply"].startswith("Tushundim. Bu registratsiya muammosi emas")
    assert "Telefonni" not in body["reply"]  # the fee question is not continued
    assert body["options"] == []


def test_new_goal_replaces_an_open_tree_question() -> None:
    with TestClient(create_app()) as client:
        first = _post(
            client, "Telefonni do'kondan O'zbekistonda oldim, ro'yxatdan o'tmayapti", "ic-4"
        )
        assert first["options"]  # a tree question is open
        body = _post(client, "Elektron chekni qayerdan olaman? To'lov qildim", "ic-4")
    assert body["reply"].startswith("Tushundim, sizga to'lovning rasmiy elektron tasdig'i")
    assert body["options"] == []


def test_an_unanswered_fee_question_is_never_repeated() -> None:
    with TestClient(create_app()) as client:
        _post(client, "Registratsiya juda qimmat.", "ic-5")
        body = _post(client, "bilmadim", "ic-5")
    assert "chetdan o'zingiz olib kelganmisiz" not in body["reply"]


def test_a_tree_question_is_never_asked_twice_in_a_row() -> None:
    with TestClient(create_app()) as client:
        first = _post(
            client, "Telefonni do'kondan O'zbekistonda oldim, ro'yxatdan o'tmayapti", "ic-6"
        )
        second = _post(client, "hmm, bilmayman nima deyishni", "ic-6")
    assert first["options"]
    assert second["reply"] != first["reply"]


def test_successful_registration_is_not_sent_into_the_failure_tree() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, _RECEIPT_EN, "ic-7")
    assert body["card_id"] is None
    assert body["known_facts"]["registration_status"] == "success"
