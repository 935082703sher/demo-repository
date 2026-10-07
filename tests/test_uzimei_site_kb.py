"""uzimei.uz site services (online registration, Birda/MyGov, payment by application
number, status check) are in the knowledge base and found by the words customers use."""

from __future__ import annotations

from functools import lru_cache

import pytest

from app.services.kb_retriever import KBChunk, KBRetriever
from kb.src import build_kb


@lru_cache(maxsize=1)
def _retriever() -> KBRetriever:
    rows, _qa, _letters = build_kb.build_rows()
    return KBRetriever([KBChunk.from_row(r) for r in rows])


@pytest.mark.parametrize(
    ("query", "title_part"),
    [
        ("Menga Imeini online royxatdan otkazishga yordam kerak", "onlayn ro‘yxatdan"),
        ("Birda orqali qilsa boladimi", "Birda"),
        ("ariza raqami keldi qanday tolayman", "Ariza raqami"),
        ("imei royxatdan otganini qanday bilaman", "ro‘yxatdan o‘tganini"),
    ],
)
def test_site_service_questions_find_the_site_entry_first(query: str, title_part: str) -> None:
    top = _retriever().retrieve(query, 1, domain="imei")[0].chunk
    assert top.doc_id == "uzimei-sayt"
    assert title_part in top.title


def test_site_entries_invent_no_new_figures() -> None:
    # Only the site's own text: no fee, deadline or count beyond what it states.
    from kb.src.uzimei_site_data import SITE

    for entry in SITE:
        digits = {tok for tok in entry["a"].replace("*", " ").split() if tok.isdigit()}
        assert digits <= {"1", "2", "3", "4", "5", "18", "240", "1170"}
