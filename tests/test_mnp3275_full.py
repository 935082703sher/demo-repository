"""MNP legal corpus from 3275-son "Telekommunikatsiya xizmatlarini ko'rsatish qoidalari".

Every MNP rule (10-§ clauses 167-226, the MNP definitions and the related clauses
elsewhere in the Rules) is searchable with its clause number; questions in uz / ru / en
find the right clause; current text outranks amendment history; and the conversation
answers MNP questions naturally without inventing a status.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.intent_control import (
    ROAMING_DEBT_AFTER_PORT,
    WRONG_PORT,
    detect_intent,
    roaming_debt_reply,
    wrong_port_reply,
)
from app.services.kb_retriever import KBChunk, KBRetriever
from app.services.status_capability import claims_live_check
from kb.src import build_kb

_DATA = Path(__file__).resolve().parents[1] / "kb" / "data" / "mnp_3275_full.json"


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    return dict(json.loads(_DATA.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _rows() -> tuple[dict[str, Any], ...]:
    rows, _qa, _letters = build_kb.build_rows()
    return tuple(rows)


@lru_cache(maxsize=1)
def _retriever() -> KBRetriever:
    return KBRetriever([KBChunk.from_row(r) for r in _rows()])


def _top(query: str, k: int = 3) -> list[str]:
    return [hit.chunk.doc_id for hit in _retriever().retrieve(query, k)]


def _unit(key: str) -> dict[str, Any]:
    return next(u for u in _data()["units"] if u["key"] == key)


# --- the corpus is complete ---------------------------------------------------------


def test_every_mnp_clause_of_paragraph_10_is_indexed() -> None:
    clauses = {u["clause"] for u in _data()["units"]}
    assert {str(n) for n in range(167, 227)} <= clauses  # 10-§ in full
    # MNP-related clauses outside 10-§
    assert {"19", "20", "251", "256", "258", "270", "296", "318", "324", "339", "373"} <= clauses


def test_mnp_definitions_are_separate_units() -> None:
    keys = {u["key"] for u in _data()["units"]}
    for term in (
        "kochib_otishi",
        "donor",
        "retsipiyent",
        "birlamchi_operator",
        "krmb",
        "krmb_operatori",
        "lokal_baza",
        "sinxronlash",
        "rn",
        "all_call_query",
        "onward_routing",
        "xato_kochirish",
    ):
        assert f"def:{term}" in keys


@pytest.mark.parametrize(
    ("key", "phrase"),
    [
        ("168", "30 kalendar kun mobaynida koʻpi bilan bir marta"),
        ("169", "raqamni terish formatining oʻzgartirilishiga yoʻl qoʻyilmaydi"),
        ("180", "8 ish soatidan koʻp boʻlmagan"),
        ("187", "3 ish soatidan koʻp boʻlmagan"),
        ("207", "donor tomonidan amalga oshiriladi"),
        ("208#aniqlash", "30 kalendar kun davomida"),
        ("208#tolash_muddati", "7 ish kunidan oshmasligi"),
        ("195", "rad etishi mumkin"),
        ("194", "SMS-xabarni yuborish orqali"),
        ("179#malumot_ozgarishi", "talabnomani berishdan oldin donor bilan tuzilgan"),
        ("183#toliq", "toʻliq rad etilgan hisoblanadi"),
        ("183#qisman", "rad javobi hisoblanmaydi"),
        ("270", "ishonchnoma"),
    ],
)
def test_key_rules_keep_their_clause_number_and_text(key: str, phrase: str) -> None:
    unit = _unit(key)
    assert phrase in unit["text"]
    assert unit["legal_refs"] == [f"3275-son Qoidalar, {unit['clause']}-band"]


def test_roaming_debt_flow_is_split_into_searchable_steps() -> None:
    keys = {u["key"] for u in _data()["units"] if u["clause"] == "208"}
    assert keys == {
        "208#aniqlash",
        "208#tolash_muddati",
        "208#krmb_tekshiruv",
        "208#xabarnoma",
        "208#cheklash",
        "208#blokdan_chiqarish",
    }


def test_rejection_reasons_have_symptom_cause_resolution_and_basis() -> None:
    reasons = {r["id"]: r for r in _data()["rejection_reasons"]}
    assert {
        "notogri_talabnoma",
        "malumot_mos_emas",
        "30_kun",
        "aktiv_talabnoma",
        "qarzdorlik",
        "majburiyat",
        "bloklangan",
    } <= set(reasons)
    for r in reasons.values():
        assert r["symptom"] and r["cause"] and r["resolution"] and r["legal_refs"]
    # identity mismatch never asks the customer to post sensitive data in chat
    assert any("Chatda" in step for step in reasons["malumot_mos_emas"]["resolution"])


def test_build_layers_counts_and_domain() -> None:
    rows = _rows()
    current = [r for r in rows if r["source_type"] == "mnp_nizom_current"]
    guides = [r for r in rows if r["source_type"] == "mnp_rejection_guide"]
    notes = [r for r in rows if r["source_type"] == "mnp_nizom_historical_note"]
    assert len(current) >= 104 and len(guides) == 7 and notes
    assert all(r["domain"] == "mnp" and r["authority"] == 2 for r in current)
    assert all(r["authority"] == 5 and r["temporal_status"] == "historical_note" for r in notes)
    assert all(r["case_type"].startswith("mnp_") for r in current + guides)
    # the FAQ and clean KB MNP articles are still there
    assert any(r["source_type"] == "faq" and r["domain"] == "mnp" for r in rows)
    assert any(r["doc_id"] == "KB-MNP-006" for r in rows)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))


# --- retrieval ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("MNP nima?", {"kb-mnp3275:def:kochib_otishi", "KB-MNP-001"}),
        ("Raqamni boshqa operatorga o'tkazsam raqam o'zgaradimi?", {"kb-mnp3275:169"}),
        ("Qancha vaqtda MNP qilinadi?", {"kb-mnp3275:180"}),
        ("Bir oyda ikki marta operator almashtirsam bo'ladimi?", {"kb-mnp3275:168"}),
        (
            "MNP nega rad etildi?",
            {
                "kb-mnp3275:rad:notogri_talabnoma",
                "kb-mnp3275:rad:30_kun",
                "kb-mnp3275:rad:majburiyat",
            },
        ),
        (
            "Ma'lumotlarim mos emas deyapti.",
            {"kb-mnp3275:rad:malumot_mos_emas", "kb-mnp3275:179#malumot_ozgarishi"},
        ),
        ("Eski operatorga qarzim bor, MNP bo'ladimi?", {"kb-mnp3275:rad:qarzdorlik"}),
        ("Raqam bloklangan bo'lsa ko'chirish mumkinmi?", {"kb-mnp3275:rad:bloklangan"}),
        ("MNP arizamni bekor qila olamanmi?", {"kb-mnp3275:195"}),
        ("Balansdagi pulim nima bo'ladi?", {"kb-mnp3275:207"}),
        ("MNPdan keyin rouming qarzi chiqsa nima bo'ladi?", {"kb-mnp3275:208#aniqlash"}),
        (
            "Eski operator qancha vaqt ichida rouming qarzini talab qilishi mumkin?",
            {"kb-mnp3275:208#aniqlash"},
        ),
        ("Rouming qarzini necha kunda to'lash kerak?", {"kb-mnp3275:208#tolash_muddati"}),
        ("KRMB nima?", {"kb-mnp3275:def:krmb"}),
        ("Donor nima?", {"kb-mnp3275:def:donor"}),
        ("Retsipiyent nima?", {"kb-mnp3275:def:retsipiyent"}),
        ("Xato ko'chirish nima?", {"kb-mnp3275:def:xato_kochirish"}),
        ("Bir nechta raqamni bir vaqtda ko'chirish mumkinmi?", {"kb-mnp3275:183#toliq"}),
        ("MNP muvaffaqiyatli tugaganini qayerdan bilaman?", {"kb-mnp3275:194"}),
        ("Otamning raqamini men ko'chirib bera olamanmi?", {"kb-mnp3275:270"}),
        ("Donor necha soatda ko'rib chiqadi?", {"kb-mnp3275:187"}),
        # ru
        ("Что такое MNP?", {"kb-mnp3275:def:kochib_otishi", "KB-MNP-001"}),
        (
            "Почему отказали в переносе номера?",
            {
                "kb-mnp3275:rad:notogri_talabnoma",
                "kb-mnp3275:rad:30_kun",
                "kb-mnp3275:rad:majburiyat",
            },
        ),
        ("Переносится ли баланс?", {"kb-mnp3275:207"}),
        ("Сколько занимает перенос номера?", {"kb-mnp3275:180"}),
        ("Можно ли отменить перенос номера?", {"kb-mnp3275:195"}),
        ("Что такое оператор-донор?", {"kb-mnp3275:def:donor"}),
        ("Что такое оператор-реципиент?", {"kb-mnp3275:def:retsipiyent"}),
        ("Что такое KRMB?", {"kb-mnp3275:def:krmb"}),
        # en
        ("What is mobile number portability?", {"kb-mnp3275:def:kochib_otishi"}),
        ("How long does number porting take?", {"kb-mnp3275:180"}),
        (
            "Why can an MNP request be rejected?",
            {
                "kb-mnp3275:rad:notogri_talabnoma",
                "kb-mnp3275:rad:30_kun",
                "kb-mnp3275:rad:majburiyat",
            },
        ),
        ("Does my balance move to the new operator?", {"kb-mnp3275:207"}),
        ("Can I cancel a porting request?", {"kb-mnp3275:195"}),
        ("What is the donor operator?", {"kb-mnp3275:def:donor"}),
        ("What is the recipient operator?", {"kb-mnp3275:def:retsipiyent"}),
    ],
)
def test_mnp_questions_find_the_right_clause(query: str, expected: set[str]) -> None:
    assert expected & set(_top(query))


def test_clause_reference_finds_its_band() -> None:
    assert "kb-mnp3275:168" in _top("168-band nima deydi?")


def test_mnp_history_only_for_history_questions() -> None:
    assert all("tarix" not in d for d in _top("MNP huquqi qanday?", 5))
    assert "kb-mnp3275:tarix:318" in _top("318-band qachon o'zgargan?")


# --- the conversation --------------------------------------------------------------


def _post(client: TestClient, message: str, session: str, lang: str = "uz") -> dict[str, Any]:
    return dict(
        client.post(
            "/assistant/converse",
            json={"message": message, "session_id": session, "language": lang},
        ).json()
    )


def test_debt_rejection_is_answered_without_irrelevant_questions() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "MNP qildim, qarzdorlik sabab rad bo'ldi.", "mnp-e2e-1")
    reply = body["reply"].lower()
    assert "qarz" in reply and "qayta" in reply  # pay the debt, then re-apply
    assert "qaysi operator" not in reply and "jismoniy shaxsmi" not in reply
    assert not claims_live_check(body["reply"])


def test_mnp_status_request_is_honest() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "MNP statusini tekshirib bering.", "mnp-e2e-2")
    assert "MNP/KRMB" in body["reply"] and "tekshira olmayman" in body["reply"]
    assert "SMS" in body["reply"] and "yuboring" in body["reply"]
    assert not claims_live_check(body["reply"])


def test_mnp_cancel_question_is_not_answered_with_imei_law() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "MNP arizamni bekor qila olamanmi?", "mnp-e2e-3")
    # never the IMEI law (VMQ-778 clauses) - with the corpus built it cites clause 195
    assert not any("VMQ-778" in s["doc_id"] for s in body["sources"])
    assert "VMQ-778" not in body["reply"] and "register_on_uzimei" not in body["reply"]


def test_wrong_port_is_treated_as_high_risk() -> None:
    assert detect_intent("Raqamimni men so'ramasdan boshqa operatorga ko'chirishdi") == WRONG_PORT
    assert detect_intent("Мой номер перенесли по ошибке") == WRONG_PORT
    assert detect_intent("Xato ko'chirish nima?") is None  # a definition question
    with TestClient(create_app()) as client:
        body = _post(
            client, "Raqamimni men so'ramasdan boshqa operatorga ko'chirishdi", "mnp-e2e-4"
        )
    assert "216-band" in body["reply"] and "toʻlov olinmaydi" in body["reply"]
    assert body["options"] == []


def test_roaming_debt_after_porting_flow() -> None:
    message = "MNPdan keyin rouming qarzi chiqsa nima bo'ladi?"
    assert detect_intent(message) == ROAMING_DEBT_AFTER_PORT
    with TestClient(create_app()) as client:
        body = _post(client, message, "mnp-e2e-5")
    reply = body["reply"]
    assert "30 kalendar kun" in reply and "7 ish kun" in reply and "15 daqiqa" in reply
    assert "186-band" in reply and "208-band" in reply


@pytest.mark.parametrize("lang", ["uz", "uz_cyrl", "ru", "en", "kaa"])
def test_mnp_intent_replies_exist_and_claim_no_lookup(lang: str) -> None:
    for reply in (wrong_port_reply(lang), roaming_debt_reply(lang)):
        assert reply.strip() and not claims_live_check(reply)
