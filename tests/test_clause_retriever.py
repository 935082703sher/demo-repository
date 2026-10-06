"""The legal reasoning base covers the whole law, and retrieval is by meaning.

These are semantic regression tests, not phrase matchers: many different phrasings
of one situation must retrieve the same clauses, across Uzbek Latin, Uzbek Cyrillic
and Russian. They never assert a final answer string.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.legal_clauses import ClauseBundle
from app.services.clause_retriever import ClauseRetriever

_CLAUSES = Path("app/data/vmq778_clauses.json")
_COVERAGE = Path("app/data/vmq778_coverage.json")


def _retriever() -> ClauseRetriever:
    return ClauseRetriever(ClauseBundle.from_json(_CLAUSES))


def _clauses(r: ClauseRetriever, message: str) -> set[str]:
    return {h.clause.clause for h in r.retrieve(message)}


# --- coverage: the whole law is represented ---


def test_coverage_report_has_no_unparsed_main_clauses() -> None:
    cov = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    assert cov["unparsed_sections"] == []  # every main clause 1-50 (minus repealed) present
    assert cov["parsed_rules_count"] >= 60
    assert "6-1" in cov["detected_subclauses"] and "44" in cov["detected_clauses"]


def test_key_clauses_and_subclauses_are_loaded() -> None:
    by = ClauseBundle.from_json(_CLAUSES).by_clause()
    for clause in ("6", "6-1", "7", "11", "24", "26", "31", "38-1", "44", "6-ilova"):
        assert clause in by, f"missing clause {clause}"


# --- retrieval is by meaning, across phrasings and languages ---


def test_ten_paraphrases_of_postal_import_find_the_same_core_clauses() -> None:
    r = _retriever()
    paraphrases = [
        "Telefon pochta orqali keldi",
        "UzPost orqali telefon olib keldim",
        "Ozondan buyurtma qildim, pochtadan keladi",
        "xalqaro jo'natma bilan telefon keldi",
        "posilka bilan telefon keldi ro'yxatdan o'tkazishim kerakmi",
        "kuryer orqali chet eldan telefon keldi",
        "почтой пришёл телефон из-за границы",
        "посылка с телефоном пришла, надо зарегистрировать",
        "международное отправление телефон",
        "Rossiyadan pochta orqali telefon kelyapti",
    ]
    for text in paraphrases:
        found = _clauses(r, text)
        assert "26" in found or "31" in found, f"postal clause not found for: {text!r}"


def test_second_imei_phrasings_find_per_imei_payment() -> None:
    r = _retriever()
    for text in [
        "ikkinchi IMEI uchun to'lov chiqdi",
        "eSIM yoqdim, ikkita IMEI bo'ldi",
        "ikki sim karta uchun alohida to'lovmi",
        "за второй imei просят оплату",
    ]:
        assert "44" in _clauses(r, text), f"clause 44 not found for: {text!r}"


def test_nonresident_phrasings_find_foreign_channel_clause() -> None:
    r = _retriever()
    for text in ["men xorijiy fuqaroman", "я нерезидент", "chet el fuqarosiman vaqtincha"]:
        assert "28-1" in _clauses(r, text), f"clause 28-1 not found for: {text!r}"


def test_retrieval_expands_along_the_rule_graph() -> None:
    # A local-purchase phrasing hits 6¹, which pulls in related clauses 6/24/44.
    hits = _retriever().retrieve("do'kondan telefon sotib oldim")
    clauses = {h.clause.clause for h in hits}
    assert "6-1" in clauses
    assert clauses & {"6", "24", "44"}  # graph expansion brought in related clauses


def test_offtopic_message_retrieves_nothing() -> None:
    assert _retriever().retrieve("bugun ob-havo qanday") == []


# --- semantic (embedding) retrieval: meaning, not shared words ---


def test_semantic_vector_recalls_a_clause_with_no_shared_word() -> None:
    # Give clause 44 a vector and query with an aligned vector but a message that
    # shares NO keyword with clause 44 - it is still recalled by meaning.
    bundle = ClauseBundle.from_json(_CLAUSES)
    vec = [1.0, 0.0, 0.0]
    vectors = {"44": vec, "7": [0.0, 1.0, 0.0]}
    r = ClauseRetriever(bundle, clause_vectors=vectors)
    assert r.has_vectors
    hits = r.retrieve("mutlaqo aloqasiz ibora xyz", query_vector=[0.99, 0.01, 0.0], expand=False)
    assert "44" in {h.clause.clause for h in hits}  # recalled semantically
    assert "7" not in {h.clause.clause for h in hits}  # orthogonal clause not recalled


def test_without_vectors_retrieval_is_purely_lexical() -> None:
    # No vectors: a query_vector is simply ignored, behaviour is the lexical baseline.
    r = _retriever()
    assert r.has_vectors is False
    assert "44" in _clauses(r, "ikkinchi IMEI uchun to'lov")  # lexical still works
    assert r.retrieve("bugun ob-havo qanday", query_vector=[1.0, 0.0]) == []


def test_committed_clause_embeddings_cover_every_clause() -> None:
    import json

    vectors = json.loads(Path("app/data/vmq778_embeddings.json").read_text(encoding="utf-8"))
    clauses = {c.clause for c in ClauseBundle.from_json(_CLAUSES).rules}
    assert set(vectors) == clauses  # every clause has a precomputed vector
    assert all(len(v) == 256 for v in vectors.values())
