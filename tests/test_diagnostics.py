"""Diagnostic engine and /assistant/diagnostics endpoints."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import kb_retriever
from app.services.diagnostic_engine import DiagnosticEngine

_DIAGNOSTICS = Path(__file__).resolve().parents[1] / "app" / "data" / "diagnostics.json"

_CORPUS_ROWS = [
    {
        "id": "faq-1", "doc_id": "faq-mnp-imei", "source_type": "faq",
        "source_title": "FAQ", "title": "MNP arizasi rad etilishi", "authority": 3,
        "domain": "mnp", "case_type": "mnp_ariza_rad", "outcome": None,
        "text": "MNP arizasi to'rt sabab bilan rad etiladi.", "legal_refs": [],
        "tags": ["mnp"], "lang": "uz_latn",
    },
    {
        "id": "reg-1", "doc_id": "VMQ 778-son", "source_type": "nizom",
        "source_title": "VMQ 778-son", "title": "Klon IMEI", "authority": 2,
        "domain": "imei", "case_type": "klon_imei", "outcome": None,
        "text": "Klonlangan IMEI ro'yxatga olinmaydi.", "legal_refs": ["VMQ 778-son"],
        "tags": ["klon"], "lang": "uz_latn",
    },
    {
        "id": "letter-1", "doc_id": "umumiy-0009", "source_type": "javob_xati",
        "source_title": "Namuna", "title": "", "authority": 4,
        "domain": "mnp", "case_type": "mnp_ariza_rad", "outcome": "rad",
        "text": "Qarzdorlik sababli ariza rad etilgani tushuntirildi.", "legal_refs": [],
        "tags": [], "lang": "uz_latn",
    },
]


def _engine() -> DiagnosticEngine:
    return DiagnosticEngine.from_json(_DIAGNOSTICS)


def test_engine_loads_and_validates() -> None:
    engine = _engine()  # raises DiagnosticError on any broken reference
    assert {t.id for t in engine.trees()} == {
        "imei-royxatdan_otkazish",
        "mnp-mnp_ariza_rad",
        "imei-blokdan_chiqarish",
        "imei-yoqotilgan_ogirlangan",
        "mnp-mnp_tartib",
    }


def test_match_tree_by_free_text() -> None:
    engine = _engine()
    imei = engine.match_tree("IMEI ro'yxatdan o'tmayapti")
    mnp = engine.match_tree("MNP arizam rad etildi")
    assert imei is not None and imei.id == "imei-royxatdan_otkazish"
    assert mnp is not None and mnp.id == "mnp-mnp_ariza_rad"
    assert engine.match_tree("bugungi ob-havo") is None


def test_engine_advances_imei_to_customs_card() -> None:
    engine = _engine()
    node, card = engine.answer("imei-royxatdan_otkazish", "source", "abroad")
    assert node is not None and node.id == "customs" and card is None
    node, card = engine.answer("imei-royxatdan_otkazish", "customs", "yes")
    assert card is not None and card.id == "imei-customs"


def test_invalid_answer_returns_nothing() -> None:
    engine = _engine()
    node, card = engine.answer("imei-royxatdan_otkazish", "source", "nonsense")
    assert node is None and card is None


@pytest.fixture
def corpus_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    corpus = tmp_path / "kb.jsonl"
    corpus.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in _CORPUS_ROWS) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KB_CORPUS_PATH", str(corpus))
    kb_retriever.get_retriever.cache_clear()
    with TestClient(create_app()) as client:
        yield client
    kb_retriever.get_retriever.cache_clear()


def test_trees_endpoint_lists_all(corpus_client: TestClient) -> None:
    body = corpus_client.get("/assistant/diagnostics/trees").json()
    assert {
        "royxatdan_otkazish",
        "mnp_ariza_rad",
        "blokdan_chiqarish",
        "yoqotilgan_ogirlangan",
        "mnp_tartib",
    } <= {t["case_type"] for t in body}


def test_step_start_returns_root_question(corpus_client: TestClient) -> None:
    body = corpus_client.post(
        "/assistant/diagnostics/step", json={"query": "MNP arizam rad etildi"}
    ).json()
    assert body["tree_id"] == "mnp-mnp_ariza_rad"
    assert body["node"]["node_id"] == "reason"
    assert any(o["value"] == "debt" for o in body["node"]["options"])


def test_step_resolves_card_with_facts_and_guidance(corpus_client: TestClient) -> None:
    body = corpus_client.post(
        "/assistant/diagnostics/step",
        json={"tree_id": "mnp-mnp_ariza_rad", "node_id": "reason", "answer": "debt"},
    ).json()
    assert body["done"] is True
    card = body["card"]
    assert card["id"] == "mnp-debt"
    assert card["steps"], "kutilgan qadamlar yo'q"
    # Part 3: fact linked to the knowledge base
    assert any(s["doc_id"] == "faq-mnp-imei" for s in card["kb_sources"])
    # Part 4: anonymized practice letter attached as guidance
    assert any(g["doc_id"] == "umumiy-0009" for g in card["case_guidance"])


def test_step_no_match_escalates(corpus_client: TestClient) -> None:
    body = corpus_client.post(
        "/assistant/diagnostics/step", json={"query": "bugungi kurs qancha"}
    ).json()
    assert body["requires_human"] is True
    assert body["message"] == "no_matching_tree"


def _diagnose(client: TestClient, **body: object) -> dict[str, Any]:
    result: dict[str, Any] = client.post("/assistant/diagnose", json=body).json()
    return result


def test_diagnose_starts_with_matched_tree(corpus_client: TestClient) -> None:
    body = _diagnose(corpus_client, message="IMEI royxatdan otmayapti")
    assert body["tree_id"] == "imei-royxatdan_otkazish"
    assert body["node_id"] == "source"
    assert body["done"] is False
    assert body["options"]


def test_diagnose_maps_free_text_answer_to_next_question(corpus_client: TestClient) -> None:
    body = _diagnose(
        corpus_client,
        message="chetdan sotib oldim",
        tree_id="imei-royxatdan_otkazish",
        node_id="source",
    )
    assert body["node_id"] == "customs"
    assert body["done"] is False


def test_diagnose_resolves_to_grounded_card(corpus_client: TestClient) -> None:
    body = _diagnose(
        corpus_client,
        message="ha, me'yordan ortiq olib keldim",
        tree_id="imei-royxatdan_otkazish",
        node_id="customs",
    )
    assert body["done"] is True
    assert body["card_id"] == "imei-customs"
    assert body["reply"], "yechim matni bo'sh"
    assert any(s["doc_id"] == "faq-mnp-imei" for s in body["sources"])


def test_diagnose_clarifies_unmapped_answer(corpus_client: TestClient) -> None:
    body = _diagnose(
        corpus_client,
        message="zzzqqq bilmadim",
        tree_id="imei-royxatdan_otkazish",
        node_id="source",
    )
    assert body["requires_human"] is False
    assert body["node_id"] == "source"
    assert body["options"]


def test_diagnose_vague_problem_offers_routing_menu(corpus_client: TestClient) -> None:
    body = _diagnose(corpus_client, message="telefonim ishlamayapti")
    assert body["requires_human"] is False
    assert body["reason"] == "clarify"
    assert len(body["options"]) == 5  # every tree offered as a choice
    assert all(o["value"].startswith(("imei-", "mnp-")) for o in body["options"])


def test_diagnose_menu_selection_starts_tree(corpus_client: TestClient) -> None:
    body = _diagnose(corpus_client, message="imei-blokdan_chiqarish")
    assert body["tree_id"] == "imei-blokdan_chiqarish"
    assert body["node_id"] == "cause"
    assert body["done"] is False


@pytest.mark.parametrize(
    ("message", "expected_tree"),
    [
        ("telefonim bloklandi nima qilay", "imei-blokdan_chiqarish"),
        ("разблокировать телефон", "imei-blokdan_chiqarish"),
        ("telefonimni o'g'irlab ketishdi", "imei-yoqotilgan_ogirlangan"),
        ("украли телефон", "imei-yoqotilgan_ogirlangan"),
        ("raqamni boshqa operatorga ko'chirmoqchiman", "mnp-mnp_tartib"),
    ],
)
def test_new_trees_match_uz_and_ru(message: str, expected_tree: str) -> None:
    matched = _engine().match_tree(message)
    assert matched is not None and matched.id == expected_tree


def test_lost_device_flow_reaches_report_card() -> None:
    engine = _engine()
    node, card = engine.answer("imei-yoqotilgan_ogirlangan", "what_happened", "stolen")
    assert node is not None and node.id == "know_imei" and card is None
    node, card = engine.answer("imei-yoqotilgan_ogirlangan", "know_imei", "yes")
    assert card is not None and card.id == "imei-report-lost"
