"""KB retriever and /assistant endpoints (synthetic corpus, no real data)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import kb_retriever

_SYNTHETIC_ROWS = [
    {
        "id": "law-1",
        "doc_id": "orq-445-30-modda",
        "source_type": "qonun",
        "source_title": "ЎРҚ-445",
        "title": "Murojaatni ko'rib chiqish muddati",
        "authority": 1,
        "domain": "murojaat_tartibi",
        "case_type": "boshqa",
        "outcome": None,
        "text": "Murojaat 15 kun ichida ko'rib chiqiladi, zarur hollarda bir oygacha uzaytiriladi.",
        "legal_refs": ["ЎРҚ-445 28-modda"],
        "tags": ["muddat", "срок"],
        "lang": "uz_latn",
    },
    {
        "id": "faq-1",
        "doc_id": "faq-imei-check",
        "source_type": "faq",
        "source_title": "IMEI FAQ",
        "title": "IMEI kodni qanday bilish mumkin",
        "authority": 3,
        "domain": "imei",
        "case_type": "royxatdan_otkazish",
        "outcome": None,
        "text": "IMEI kodni bilish uchun telefonda *#06# tering.",
        "legal_refs": [],
        "tags": ["imei", "kod"],
        "lang": "uz_latn",
    },
    {
        "id": "letter-1",
        "doc_id": "letter-sample",
        "source_type": "javob_xati",
        "source_title": "Namuna xat",
        "title": "MNP arizasi",
        "authority": 4,
        "domain": "mnp",
        "case_type": "mnp_ariza_rad",
        "outcome": "rad",
        "text": "Qarzdorlik sababli MNP arizasi rad etildi.",
        "legal_refs": [],
        "tags": ["mnp"],
        "lang": "uz_latn",
    },
]


@pytest.fixture
def corpus_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    corpus = tmp_path / "kb.jsonl"
    corpus.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in _SYNTHETIC_ROWS) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KB_CORPUS_PATH", str(corpus))
    kb_retriever.get_retriever.cache_clear()
    with TestClient(create_app()) as client:
        yield client
    kb_retriever.get_retriever.cache_clear()


def test_health_reports_corpus_and_mode(corpus_client: TestClient) -> None:
    body = corpus_client.get("/assistant/health").json()
    assert body["chunks"] == 3
    assert body["mode"] == "bm25_only"
    assert body["layers"] == {"1": 1, "3": 1, "4": 1}


def test_taxonomy_exposes_filter_axes(corpus_client: TestClient) -> None:
    body = corpus_client.get("/assistant/taxonomy").json()
    assert set(body) == {"domain", "case_type", "outcome"}
    assert "imei" in body["domain"]


def test_retrieve_returns_grounded_context_and_prompt(corpus_client: TestClient) -> None:
    response = corpus_client.post(
        "/assistant/retrieve", json={"query": "IMEI kodni qanday bilaman"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "bm25_only"
    assert body["sources"], "kutilgan manba topilmadi"
    assert body["sources"][0]["doc_id"] == "faq-imei-check"
    assert "*#06#" in body["context"]
    assert "doc_id" in body["system_prompt"] or "faq-imei-check" in body["system_prompt"]


def test_retrieve_supports_cyrillic_query(corpus_client: TestClient) -> None:
    response = corpus_client.post(
        "/assistant/retrieve", json={"query": "Срок рассмотрения обращения"}
    )
    body = response.json()
    assert any(source["doc_id"] == "orq-445-30-modda" for source in body["sources"])


def test_domain_filter_restricts_results(corpus_client: TestClient) -> None:
    response = corpus_client.post(
        "/assistant/retrieve",
        json={"query": "ariza", "domain": "mnp"},
    )
    body = response.json()
    assert all(source["domain"] == "mnp" for source in body["sources"])


def test_unmatched_query_returns_no_sources(corpus_client: TestClient) -> None:
    response = corpus_client.post("/assistant/retrieve", json={"query": "zzzqqqxxx"})
    body = response.json()
    assert body["sources"] == []


def test_missing_corpus_reports_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KB_CORPUS_PATH", str(tmp_path / "absent.jsonl"))
    kb_retriever.get_retriever.cache_clear()
    with TestClient(create_app()) as client:
        body = client.get("/assistant/health").json()
    kb_retriever.get_retriever.cache_clear()
    assert body["chunks"] == 0
    assert body["mode"] == "unavailable"


def test_answer_generates_grounded_answer(corpus_client: TestClient) -> None:
    response = corpus_client.post(
        "/assistant/answer", json={"query": "IMEI kodni qanday bilaman", "language": "uz"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requires_human"] is False
    assert body["answer"]  # mock provider echoes the top grounded passage
    assert body["citations"], "kutilgan iqtibos yo'q"
    assert any(source["doc_id"] == "faq-imei-check" for source in body["sources"])
    assert body["model"]


def test_answer_without_match_escalates_without_llm(corpus_client: TestClient) -> None:
    response = corpus_client.post("/assistant/answer", json={"query": "zzzqqqxxx"})
    body = response.json()
    assert body["answer"] is None
    assert body["requires_human"] is True
    assert body["reason"] == "no_approved_source"


def test_answer_handles_provider_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.domain.schemas import LLMRequest, LLMResult
    from app.providers.errors import ProviderUnavailableError

    class _FailingProvider:
        async def generate(self, request: LLMRequest) -> LLMResult:
            raise ProviderUnavailableError("down")

    corpus = tmp_path / "kb.jsonl"
    corpus.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in _SYNTHETIC_ROWS) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KB_CORPUS_PATH", str(corpus))
    kb_retriever.get_retriever.cache_clear()
    with TestClient(create_app(provider=_FailingProvider())) as client:
        body = client.post("/assistant/answer", json={"query": "IMEI kodni bilaman"}).json()
    kb_retriever.get_retriever.cache_clear()
    assert body["answer"] is None
    assert body["requires_human"] is True
    assert body["reason"] == "provider_unavailable"
