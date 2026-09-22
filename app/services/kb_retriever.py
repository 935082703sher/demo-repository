"""BM25 knowledge-base retriever over the four-layer RTMC corpus.

Reads the built corpus (``kb/out/kb.jsonl`` by default; gitignored, sensitive
provenance) and serves lexical retrieval with authority-layer metadata plus a
ready-to-use system prompt. No external dependency and no LLM call: the
generation layer is composed on top of ``/assistant/retrieve``, so retrieval can
be tested independently of whichever model is plugged in later.

When the corpus file is absent the retriever loads empty and reports an
``unavailable`` mode instead of failing, so the application still starts.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

try:  # kb/ is committed, but stay defensive if the package is stripped.
    from kb.src.normalize import normalize as _kb_normalize
except Exception:  # pragma: no cover - exercised only without the kb package
    _kb_normalize = None

try:
    from kb.src.taxonomy import CASE_TYPES, DOMAINS, OUTCOMES
except Exception:  # pragma: no cover
    DOMAINS = {}
    CASE_TYPES = {}
    OUTCOMES = {}

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "kb" / "out" / "kb.jsonl"
_TOKEN = re.compile(r"[a-z0-9]{3,}")

MODE_HYBRID_UNAVAILABLE = "bm25_only"
MODE_EMPTY = "unavailable"

_SYSTEM_PROMPT_HEADER = (
    "Siz RTMC/O'zTTBRM murojaatlar bo'yicha AI yordamchisisiz. Faqat quyidagi "
    "tasdiqlangan kontekstdan foydalaning. Faktlarni (muddat, to'lov, tartib, "
    "huquqiy norma) faqat yuqori qatlam manbalaridan oling: qonun (authority=1), "
    "nizom (authority=2), FAQ (authority=3). Javob xatlari (authority=4) faqat "
    "uslub va kazus namunasi — ulardan aniq raqam yoki normani olmang. Kontekstda "
    "javob bo'lmasa, hech narsa o'ylab topmang va operatorga yo'naltiring. Har bir "
    "fakt uchun manba doc_id sini keltiring. Foydalanuvchi tilida javob bering."
)


def _normalize(text: str) -> str:
    if _kb_normalize is not None:
        return str(_kb_normalize(text))
    return text.lower()


def corpus_path() -> Path:
    """Return the corpus path, overridable via ``KB_CORPUS_PATH``."""
    override = os.environ.get("KB_CORPUS_PATH")
    return Path(override) if override else _DEFAULT_CORPUS


def default_top_k() -> int:
    """Return the default chunk count, overridable via ``KB_TOP_K``."""
    try:
        return max(1, int(os.environ.get("KB_TOP_K", "8")))
    except ValueError:
        return 8


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(_normalize(text))


@dataclass(frozen=True)
class KBChunk:
    """One retrievable corpus chunk with its authority-layer metadata."""

    id: str
    doc_id: str
    source_type: str
    source_title: str
    title: str
    authority: int
    domain: str
    case_type: str
    outcome: str | None
    text: str
    legal_refs: tuple[str, ...]
    tags: tuple[str, ...]
    lang: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> KBChunk:
        return cls(
            id=str(row.get("id", "")),
            doc_id=str(row.get("doc_id", "")),
            source_type=str(row.get("source_type", "")),
            source_title=str(row.get("source_title", "") or row.get("title", "")),
            title=str(row.get("title", "")),
            authority=int(row.get("authority", 4) or 4),
            domain=str(row.get("domain", "boshqa")),
            case_type=str(row.get("case_type", "boshqa")),
            outcome=str(row["outcome"]) if row.get("outcome") else None,
            text=str(row.get("text", "")),
            legal_refs=tuple(str(x) for x in (row.get("legal_refs") or [])),
            tags=tuple(str(x) for x in (row.get("tags") or [])),
            lang=str(row.get("lang", "uz_latn")),
        )

    def index_text(self) -> str:
        return f"{self.title} {' '.join(self.tags)} {self.text}"


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk paired with its lexical relevance score."""

    chunk: KBChunk
    score: float


class _BM25:
    """Minimal Okapi BM25 over pre-tokenized documents (no dependency)."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self._docs = docs
        self._k1 = k1
        self._b = b
        self._n = len(docs)
        self._avgdl = sum(len(d) for d in docs) / max(1, self._n)
        self._df: Counter[str] = Counter()
        for doc in docs:
            self._df.update(set(doc))
        self._tf: list[Counter[str]] = [Counter(doc) for doc in docs]

    def scores(self, query: list[str]) -> list[float]:
        out: list[float] = []
        for i, term_freq in enumerate(self._tf):
            length = len(self._docs[i]) or 1
            total = 0.0
            for term in query:
                freq = term_freq.get(term)
                if not freq:
                    continue
                idf = math.log(1 + (self._n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                total += (
                    idf
                    * freq
                    * (self._k1 + 1)
                    / (freq + self._k1 * (1 - self._b + self._b * length / self._avgdl))
                )
            out.append(total)
        return out


class KBRetriever:
    """Lexical retriever with authority metadata and system-prompt assembly."""

    def __init__(self, chunks: list[KBChunk]) -> None:
        self._chunks = chunks
        self._bm25 = _BM25([_tokenize(chunk.index_text()) for chunk in chunks])

    @property
    def size(self) -> int:
        return len(self._chunks)

    @property
    def mode(self) -> str:
        return MODE_HYBRID_UNAVAILABLE if self._chunks else MODE_EMPTY

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        *,
        domain: str | None = None,
        case_type: str | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top scoring chunks, optionally filtered by taxonomy axes."""
        if not self._chunks or not query.strip():
            return []
        limit = top_k or default_top_k()
        scores = self._bm25.scores(_tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        results: list[RetrievedChunk] = []
        for i in order:
            if scores[i] <= 0:
                break
            chunk = self._chunks[i]
            if domain and chunk.domain != domain:
                continue
            if case_type and chunk.case_type != case_type:
                continue
            results.append(RetrievedChunk(chunk=chunk, score=round(scores[i], 4)))
            if len(results) >= limit:
                break
        return results

    def stats(self) -> dict[str, Any]:
        layers: Counter[int] = Counter(chunk.authority for chunk in self._chunks)
        return {
            "chunks": len(self._chunks),
            "mode": self.mode,
            "layers": {str(authority): layers[authority] for authority in sorted(layers)},
        }


def build_system_prompt(query: str, results: list[RetrievedChunk]) -> str:
    """Assemble the grounded system prompt from retrieved context."""
    if not results:
        return f"{_SYSTEM_PROMPT_HEADER}\n\nKONTEKST: [bo'sh]\n\nSAVOL: {query}"
    blocks = [
        f"[{r.chunk.doc_id} | authority={r.chunk.authority} | "
        f"{r.chunk.source_type}/{r.chunk.domain}]\n{r.chunk.text}"
        for r in results
    ]
    context = "\n\n".join(blocks)
    return f"{_SYSTEM_PROMPT_HEADER}\n\nKONTEKST:\n{context}\n\nSAVOL: {query}"


def taxonomy() -> dict[str, Any]:
    """Return category filters for the frontend."""
    return {
        "domain": dict(DOMAINS),
        "case_type": {key: value[0] for key, value in CASE_TYPES.items()},
        "outcome": {key: value[0] for key, value in OUTCOMES.items()},
    }


def load_corpus(path: Path | None = None) -> list[KBChunk]:
    """Load and parse the JSONL corpus; return empty when the file is absent."""
    target = path or corpus_path()
    if not target.exists():
        return []
    chunks: list[KBChunk] = []
    with target.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                chunks.append(KBChunk.from_row(json.loads(stripped)))
    return chunks


@lru_cache(maxsize=1)
def get_retriever() -> KBRetriever:
    """Return the process-wide retriever, built once from the corpus file."""
    return KBRetriever(load_corpus())
