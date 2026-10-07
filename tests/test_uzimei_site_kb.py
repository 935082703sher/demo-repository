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


def test_startup_rebuilds_a_missing_or_stale_index(monkeypatch: pytest.MonkeyPatch) -> None:
    # A fresh clone or a `git pull` that changed the KB must not leave the assistant
    # on a missing/old index (it then answers procedure questions with "no data").
    import os
    import subprocess

    from app.services import kb_retriever

    target = kb_retriever._REPO_ROOT / "kb" / "out" / "kb.jsonl"
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[bytes]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.delenv("KB_CORPUS_PATH", raising=False)
    monkeypatch.setattr(subprocess, "run", fake_run)
    if target.exists():
        newest = kb_retriever._newest_input_mtime()
        os.utime(target, (newest - 10, newest - 10))  # older than its sources
    kb_retriever.ensure_corpus()
    assert calls and calls[0][-1].endswith("build_kb.py")

    calls.clear()
    monkeypatch.setenv("KB_CORPUS_PATH", "/explicit/index.jsonl")
    assert kb_retriever.ensure_corpus() == "skipped" and not calls
