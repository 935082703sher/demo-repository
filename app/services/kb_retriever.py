"""BM25 knowledge-base retriever over the layered RTMC corpus.

Reads the built corpus (``kb/out/kb.jsonl`` by default; gitignored, sensitive
provenance) and serves lexical retrieval with authority-layer metadata plus a
ready-to-use system prompt. No external dependency and no LLM call: the
generation layer is composed on top of ``/assistant/retrieve``, so retrieval can
be tested independently of whichever model is plugged in later.

When the corpus file is absent the retriever loads empty and reports an
``unavailable`` mode instead of failing, so the application still starts.

Ranking is not the lexical score alone. Each hit is weighted by its authority layer
(law > regulation > FAQ / approved KB > resolution cards > practice letters >
amendment history) and by its temporal status: the current consolidated text always
outranks historical material. A historical transition rule or an amendment note
("... qarori tahririda", "2019-yil 1-noyabrgacha") is pushed far down for ordinary
questions, and surfaces only when the question itself is about history ("bu band
qachon o'zgargan?", "700-son qaror bilan nima yangilangan?"), so an old revision is
never served as today's rule.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
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

# Authority layer weight (1 = law ... 5 = amendment history). Mild, so relevance still
# decides between layers of similar authority.
_AUTHORITY_WEIGHT = {1: 1.10, 2: 1.05, 3: 1.0, 4: 0.85, 5: 0.5}
# Temporal weight for an ordinary question vs. a question about history.
_TEMPORAL_WEIGHT = {"current": 1.0, "historical": 0.3, "historical_note": 0.25}
_TEMPORAL_WEIGHT_HISTORY = {"current": 1.0, "historical": 1.1, "historical_note": 1.6}
# A question about how/when the rules changed (normalised Latin form). A decree number
# other than 778 itself ("700-son qaror") also marks a history question.
_HISTORY_MARKERS = (
    "qachon ozgar",
    "ozgargan",
    "ozgartir",
    "ozgarish",
    "yangilangan",
    "tahrir",
    "kuchga kir",
    "kuchini yoqot",
    "chiqarilgan",
    "eski qoida",
    "tarixi",
    "izmen",
    "redakts",
    "utratil",
    "amend",
    "history",
    "changed",
)
# Question and filler words carry no topic. They are dropped from the QUERY (never
# from documents), so "bugungi ob-havo qanday" cannot reach the evidence floor on
# "qanday" alone - a larger corpus would otherwise inflate such words' weight.
_QUERY_STOPWORDS = frozenset(
    {
        # uz
        "qanday",
        "qancha",
        "qachon",
        "qayerda",
        "qayerdan",
        "qaerda",
        "qaerdan",
        "nima",
        "nimaga",
        "nimani",
        "nega",
        "kerak",
        "kerakmi",
        "mumkin",
        "mumkinmi",
        "bormi",
        "uchun",
        "bilan",
        "yoki",
        "lekin",
        "agar",
        "menga",
        "mening",
        "men",
        "sizga",
        "iltimos",
        "salom",
        "rahmat",
        "ham",
        # ru (normalised Latin)
        "chto",
        "kak",
        "kogda",
        "gde",
        "eto",
        "dlya",
        "ili",
        "mne",
        "moy",
        "moya",
        "menya",
        "pozhaluysta",
        "takoe",
        "kakoy",
        "kakaya",
        "kakie",
        # en
        "what",
        "how",
        "when",
        "where",
        "the",
        "and",
        "for",
        "can",
        "does",
        "with",
        "this",
        "that",
        "are",
        "you",
        "please",
        "will",
        "there",
        "about",
    }
)
_DECREE_NUMBER = re.compile(r"\b(?!778\b)\d{2,3}\s*-?\s*son")

MODE_HYBRID_UNAVAILABLE = "bm25_only"
MODE_EMPTY = "unavailable"

_SYSTEM_PROMPT_HEADER = (
    "Siz RTMC/O'zTTBRM murojaatlar bo'yicha AI yordamchisisiz. Faqat quyidagi "
    "tasdiqlangan kontekstdan foydalaning. Faktlarni (muddat, to'lov, tartib, "
    "huquqiy norma) faqat yuqori qatlam manbalaridan oling: qonun (authority=1), "
    "nizom (authority=2), FAQ (authority=3). Javob xatlari (authority=4) faqat "
    "uslub va kazus namunasi — ulardan aniq raqam yoki normani olmang. Kontekstda "
    "javob bo'lmasa, hech narsa o'ylab topmang va operatorga yo'naltiring. Har bir "
    "fakt uchun manba doc_id sini keltiring. Foydalanuvchi tilida javob bering. "
    "temporal_status=historical yoki historical_note bo'lgan manba — eski tahrir yoki "
    "tahrirlar tarixi: uni hozirgi amaldagi qoida sifatida bermang, faqat tarix haqidagi "
    "savolga javob bering. Normativ matnni katta paragraf qilib ko'chirmang: avval "
    "savolga tabiiy, qisqa javob bering, keyin kerak bo'lsa normativ asosni (masalan, "
    "VMQ 778-son Nizomining 6¹-bandi) va keyingi qadamni ayting. Foydalanuvchining real "
    "holatini (IMEI statusi, to'lov) tizimdan tekshirgandek gapirmang."
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


# "14-band", "6¹-band", "3a-ilova", "32-modda": a clause reference becomes one token
# ("band14"), so a question naming a clause finds it - the bare number alone is too
# short to be indexed.
_CLAUSE_REF = re.compile(r"(\d+[a-z]?)\s*-\s*(band|bob|ilova|modda)")
# Russian / English clause references: "пункт 49²", "clause 14" -> "band492", "band14".
_CLAUSE_REF_PREFIX = re.compile(r"\b(?:punkt|clause|paragraph)\s*(\d+[a-z]?)")


def _tokenize(text: str) -> list[str]:
    norm = _CLAUSE_REF.sub(r"\2\1", _normalize(text))
    return _TOKEN.findall(_CLAUSE_REF_PREFIX.sub(r"band\1", norm))


# "X nima?" / "что такое X" / "what is X": a definition question. Definitions (legal
# "Asosiy tushuncha" units, "... nima?" articles) get a moderate boost for it, since a
# one-word topic otherwise ranks by document length alone.
_DEFINITION_QUERY = re.compile(r"(\bnima\s*$)|(^\s*chto takoe\b)|(^\s*what (is|are)\b)")
_DEFINITION_BOOST = 1.5


def is_definition_query(query: str) -> bool:
    norm = " ".join(re.sub(r"[^\w]+", " ", _normalize(query)).split())
    return bool(_DEFINITION_QUERY.search(norm))


def _is_definition(chunk: KBChunk) -> bool:
    title = _normalize(chunk.title)
    return "asosiy tushuncha" in title or title.rstrip(" ?").endswith("nima")


# Token-set overlap above which two chunks are treated as the same rule.
_DUPLICATE_JACCARD = 0.8


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_history_query(query: str) -> bool:
    """True when the question asks how or when the rules changed, not what they are now."""
    norm = _normalize(query)
    return any(marker in norm for marker in _HISTORY_MARKERS) or bool(_DECREE_NUMBER.search(norm))


def rank_weight(chunk: KBChunk, *, history: bool) -> float:
    """Authority x temporal weight applied on top of the lexical score."""
    temporal = (_TEMPORAL_WEIGHT_HISTORY if history else _TEMPORAL_WEIGHT).get(
        chunk.temporal_status, 1.0
    )
    return _AUTHORITY_WEIGHT.get(chunk.authority, 0.85) * temporal


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
    temporal_status: str = "current"

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
            temporal_status=str(row.get("temporal_status") or "current"),
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
        docs = [_tokenize(chunk.index_text()) for chunk in chunks]
        self._bm25 = _BM25(docs)
        self._token_sets = [frozenset(d) for d in docs]

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
        """Return the top chunks by weighted score, optionally filtered by taxonomy axes.

        The lexical score is multiplied by the chunk's authority and temporal weight,
        so the current normative text outranks historical notes and practice letters
        unless the question is explicitly about history.
        """
        if not self._chunks or not query.strip():
            return []
        limit = top_k or default_top_k()
        history = is_history_query(query)
        definition = is_definition_query(query)
        terms = [t for t in _tokenize(query) if t not in _QUERY_STOPWORDS]
        if not terms:
            return []
        raw = self._bm25.scores(terms)
        scores = [
            score
            * rank_weight(chunk, history=history)
            * (_DEFINITION_BOOST if definition and _is_definition(chunk) else 1.0)
            if score > 0
            else 0.0
            for score, chunk in zip(raw, self._chunks, strict=True)
        ]
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        results: list[RetrievedChunk] = []
        kept: list[frozenset[str]] = []
        for i in order:
            if scores[i] <= 0:
                break
            chunk = self._chunks[i]
            if domain and chunk.domain != domain:
                continue
            if case_type and chunk.case_type != case_type:
                continue
            # The same rule often exists in several layers (FAQ, curated, full legal
            # text). Keep only the strongest-ranked copy so near-duplicates do not crowd
            # out other evidence; ranking already put the higher-authority copy first.
            if any(_jaccard(self._token_sets[i], other) >= _DUPLICATE_JACCARD for other in kept):
                continue
            kept.append(self._token_sets[i])
            results.append(RetrievedChunk(chunk=chunk, score=round(scores[i], 4)))
            if len(results) >= limit:
                break
        return results

    def sources_by_doc_ids(self, doc_ids: list[str]) -> list[KBChunk]:
        """Return one representative chunk per requested doc id (for citations)."""
        wanted = set(doc_ids)
        seen: dict[str, KBChunk] = {}
        for chunk in self._chunks:
            if chunk.doc_id in wanted and chunk.doc_id not in seen:
                seen[chunk.doc_id] = chunk
        return [seen[doc_id] for doc_id in doc_ids if doc_id in seen]

    def case_guidance(self, case_type: str, limit: int = 2) -> list[KBChunk]:
        """Return anonymized practice letters (layer 4) for a case type as style."""
        letters = [
            chunk for chunk in self._chunks if chunk.authority == 4 and chunk.case_type == case_type
        ]
        return letters[:limit]

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
        f"{r.chunk.source_type}/{r.chunk.domain} | {r.chunk.temporal_status}]\n{r.chunk.text}"
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


_BUILD_SCRIPT = _REPO_ROOT / "kb" / "src" / "build_kb.py"
_KB_INPUTS = (_REPO_ROOT / "kb" / "src", _REPO_ROOT / "kb" / "data")


def _newest_input_mtime() -> float:
    newest = 0.0
    for folder in _KB_INPUTS:
        if folder.is_dir():
            for item in folder.rglob("*"):
                if item.is_file() and item.suffix in {".py", ".json", ".jsonl", ".txt"}:
                    newest = max(newest, item.stat().st_mtime)
    return newest


def ensure_corpus() -> str:
    """Build the default index when it is missing or older than its KB sources.

    The index is gitignored, so after a fresh clone or a ``git pull`` that changed the
    KB it is absent or stale - and the assistant then answers procedure questions with
    "no data". Rebuilding here (a fraction of a second) removes that manual step. An
    explicit ``KB_CORPUS_PATH`` is never touched. Returns what was done.
    """
    if os.environ.get("KB_CORPUS_PATH") or not _BUILD_SCRIPT.exists():
        return "skipped"
    target = _DEFAULT_CORPUS
    if target.exists() and target.stat().st_mtime >= _newest_input_mtime():
        return "fresh"
    result = subprocess.run(
        [sys.executable, str(_BUILD_SCRIPT)],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        timeout=120,
    )
    get_retriever.cache_clear()
    return "built" if result.returncode == 0 and target.exists() else "build_failed"


@lru_cache(maxsize=1)
def get_retriever() -> KBRetriever:
    """Return the process-wide retriever, built once from the corpus file."""
    return KBRetriever(load_corpus())
