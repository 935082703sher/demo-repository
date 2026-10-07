"""VMQ 778-son full legal corpus: complete, current-first, multilingual retrieval.

The whole consolidated decree and Nizom (every chapter, clause, definition and annex)
is searchable; amendment notes and 2019 transition rules are kept apart from the
current text and surface only for questions about history.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from app.services.kb_retriever import KBChunk, KBRetriever, is_history_query
from kb.src import build_kb

_DATA = Path(__file__).resolve().parents[1] / "kb" / "data" / "vmq778_full.json"


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


def _top(query: str, k: int = 3) -> list[KBChunk]:
    return [hit.chunk for hit in _retriever().retrieve(query, k)]


# --- the corpus is complete ---------------------------------------------------------


def test_every_chapter_and_substantive_clause_is_present() -> None:
    units = _data()["units"]
    chapters = {u["chapter"].split(".")[0] for u in units if u["chapter"]}
    assert chapters == {f"{n}-bob" for n in range(1, 11)}
    clauses = {u["clause"] for u in units if u["part"] == "nizom"}
    expected = {str(n) for n in range(1, 51) if n not in (40, 41)}  # 40, 41 repealed
    expected |= {
        "6.1",
        "10.1",
        "10.2",
        "28.1",
        "29.1",
        "31.1",
        "31.2",
        "38.1",
        "49.1",
        "49.2",
        "49.3",
    }
    assert expected <= clauses
    assert {u["clause"] for u in units if u["part"] == "qaror"} == {str(n) for n in range(1, 7)}


def test_every_annex_is_present() -> None:
    annexes = {u["key"].split(":")[1] for u in _data()["units"] if u["part"] == "ilova"}
    assert annexes == {"1", "2", "3a", "3b", "3v", "3g", "4", "5", "5a", "6"}


def test_definitions_lists_and_device_categories_are_separate_units() -> None:
    keys = {u["key"] for u in _data()["units"]}
    for term in (
        "imei",
        "tac",
        "gsma",
        "msisdn",
        "tarmoq hodisasi",
        "klonlangan imei-kod",
        "aniqlanmagan imei-kod",
        "oq roʻyxat",
        "qora roʻyxat",
        "kul rang roʻyxat",
        "bogʻlangan oq roʻyxat",
    ):
        assert f"nizom:2:{term}" in keys
    assert {f"ilova:1:{n}" for n in range(1, 15)} <= keys  # 14 device categories


def test_tariff_table_is_complete_and_versioned() -> None:
    tariff = next(u for u in _data()["units"] if u["key"] == "ilova:6")
    text = tariff["text"]
    for line in (
        "Import qiluvchi: BHM",
        "Ishlab chiqaruvchi **: BHMning 10%",
        "BHMning 20%",
        "BHMning 25%",
        "Bepul",
        "Diplomatik korpus",
    ):
        assert line in text
    assert "manbada miqdor koʻrsatilmagan" in text  # row 6 has no amount in the source
    assert tariff["tariff"]["requires_current_verification"] is True
    assert tariff["tariff"]["effective_from"] == "2020-12-31"


def test_every_amendment_note_is_kept_apart_from_current_text() -> None:
    data = _data()
    assert data["stats"]["raw_change_notes"] == 61
    for unit in data["units"]:
        assert "tahririda" not in unit["text"]  # no lex.uz change notes in normative text
    targets = {h["target"] for h in data["historical_notes"]}
    assert {"nizom:40", "nizom:41"} <= targets  # repealed clauses survive as history only
    assert data["consolidated_through"] == "2026-02-08"


def test_build_has_no_duplicate_ids_and_counts_layers() -> None:
    rows = _rows()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    full = [r for r in rows if r["source_type"] == "nizom_toliq"]
    notes = [r for r in rows if r["source_type"] == "nizom_tarixiy_izoh"]
    assert len(full) >= 117 and len(notes) >= 45
    assert all(r["authority"] == 2 for r in full)
    assert all(r["authority"] == 5 and r["temporal_status"] == "historical_note" for r in notes)
    # the curated layer and the other layers are still there
    assert any(r["doc_id"] == "VMQ 778-son" for r in rows)
    assert any(r["source_type"] == "faq" for r in rows)
    assert any(r["source_type"] == "bilim_maqola" for r in rows)


def test_utf8_is_preserved() -> None:
    texts = " ".join(r["text"] for r in _rows() if r["source_type"] == "nizom_toliq")
    assert "roʻyxat" in texts and "Oʻzbekiston" in texts
    assert "�" not in texts


# --- retrieval ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "doc_id"),
    [
        ("Qora ro'yxat nima?", "kb-vmq778:nizom:2:qora roʻyxat"),
        ("Kulrang ro'yxatda qancha vaqt turadi?", "kb-vmq778:nizom:2:kul rang roʻyxat"),
        ("Klonlangan IMEI registratsiya qilinadimi?", "kb-vmq778:nizom:7"),
        ("Telefonni do'kondan olganman, kim registratsiya qilishi kerak?", "kb-vmq778:nizom:6.1"),
        (
            "Avval registratsiya qilingan telefonni qayta ro'yxatdan o'tkazish kerakmi?",
            "kb-vmq778:nizom:9",
        ),
        ("BYD ma'lumoti arizaga mos kelmasa nima bo'ladi?", "kb-vmq778:nizom:14"),
        ("Import qilingan telefon qachon registratsiya qilinadi?", "kb-vmq778:nizom:11"),
        ("Har bir IMEI uchun alohida to'lov qilinadimi?", "kb-vmq778:nizom:44"),
        ("IoT qurilmalar qanday registratsiya qilinadi?", "kb-vmq778:ilova:1:8"),
        ("Diplomatik vakolatxona telefonni qanday registratsiya qiladi?", "kb-vmq778:nizom:10.1"),
        ("Ro'yxatdan o'tgan IMEI keyinchalik bekor qilinishi mumkinmi?", "kb-vmq778:nizom:49.2"),
        ("Qaror ustidan shikoyat qilish mumkinmi?", "kb-vmq778:nizom:49.3"),
        ("Что такое серый список IMEI?", "kb-vmq778:nizom:2:kul rang roʻyxat"),
        ("Who is responsible for registering a phone sold in Uzbekistan?", "kb-vmq778:nizom:6.1"),
        ("What happens if customs declaration data does not match?", "kb-vmq778:nizom:14"),
    ],
)
def test_sample_questions_find_the_relevant_clause(query: str, doc_id: str) -> None:
    assert doc_id in [c.doc_id for c in _top(query)]


def test_current_question_never_gets_history_first() -> None:
    for query in (
        "IMEI uchun hozirgi tartib qanday?",
        "IMEI ro'yxatga olish bepulmi?",
        "Registratsiya muddati qancha?",
    ):
        top = _top(query, 5)
        assert top and top[0].temporal_status == "current"
        assert all(c.temporal_status != "historical_note" for c in top)


@pytest.mark.parametrize(
    ("query", "target"),
    [
        ("2025-yil 700-son qarori bilan nima yangilangan?", "700-son"),
        ("14-band qachon o'zgargan?", "kb-vmq778:tarix:nizom:14"),
        ("Когда изменили пункт 49²?", "kb-vmq778:tarix:nizom:49.2"),
        ("When was clause 14 changed?", "kb-vmq778:tarix:nizom:14"),
    ],
)
def test_history_questions_find_amendment_notes(query: str, target: str) -> None:
    assert is_history_query(query)
    top = _top(query)
    assert top[0].temporal_status in ("historical_note", "historical")
    assert any(target in c.doc_id or target in c.text for c in top)


def test_annex_forms_are_marked_as_empty_samples() -> None:
    form = next(c for c in _top("jismoniy shaxs anketasi namunasi", 5) if "anketa" in c.text)
    assert "chatda shaxsiy maʼlumot yuborish talab qilinmaydi" in form.text
