"""Store for expert-reviewed drafts and the versioned, published KB articles.

This is the answerable "learned knowledge" the assistant gains over time. A draft is
held until an expert approves it; approval validates it (required fields, expert
present, no duplicate title in the same domain), then publishes a new versioned
article and refreshes the searchable index immediately. Older versions are kept so a
regression can be rolled back. Search is lexical over the article's title, problem,
keywords and synonyms (normalised the same way as the rest of the system), returning
the best current (non-superseded) article above a floor - weak matches return nothing
so the assistant never answers from a thin learned match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol, runtime_checkable

from app.domain.knowledge_article import (
    DraftStatus,
    KnowledgeArticle,
    KnowledgeContent,
    KnowledgeDraft,
)
from app.services.embeddings import EmbedText
from app.services.embeddings import cosine as _cosine
from app.services.fact_extraction import _normalize


class ValidationError(Exception):
    """A draft failed publication validation (missing fields, duplicate, no expert)."""


@dataclass(frozen=True)
class ArticleHit:
    article: KnowledgeArticle
    score: float


def _tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) > 2}


@runtime_checkable
class LearnedKnowledgeStore(Protocol):
    """Drafts awaiting approval, and the published versioned articles."""

    async def add_draft(self, draft: KnowledgeDraft) -> KnowledgeDraft: ...
    async def get_draft(self, draft_id: str) -> KnowledgeDraft | None: ...
    async def list_drafts(self) -> list[KnowledgeDraft]: ...
    async def approve(
        self, draft_id: str, *, expert: str, change_reason: str = ""
    ) -> KnowledgeArticle: ...
    async def reject(self, draft_id: str) -> KnowledgeDraft | None: ...
    async def list_articles(self) -> list[KnowledgeArticle]: ...
    async def search(self, query: str) -> ArticleHit | None: ...
    async def strong_match(self, query: str) -> ArticleHit | None: ...
    async def rollback(self, article_id: str, version: int) -> KnowledgeArticle | None: ...


class InMemoryLearnedKnowledgeStore:
    """In-memory drafts + versioned articles with a lexical search index (dev/tests)."""

    def __init__(self, embed: EmbedText | None = None) -> None:
        self._drafts: dict[str, KnowledgeDraft] = {}
        self._versions: dict[str, list[KnowledgeArticle]] = {}
        self._current: dict[str, KnowledgeArticle] = {}  # article_id -> current version
        self._vectors: dict[str, list[float]] = {}  # article_id -> content embedding
        self._embed = embed
        self._seq = 0

    # Match floors differ by mode: a semantic cosine lives in [0,1], a lexical token
    # score is an integer count. "normal" is enough to answer from a learned article;
    # "strong" is required to pre-empt a diagnostic tree with one.
    _NORMAL: ClassVar[dict[str, float]] = {"semantic": 0.45, "lexical": 1.5}
    _STRONG: ClassVar[dict[str, float]] = {"semantic": 0.60, "lexical": 3.0}

    async def add_draft(self, draft: KnowledgeDraft) -> KnowledgeDraft:
        self._drafts[draft.draft_id] = draft
        return draft

    async def get_draft(self, draft_id: str) -> KnowledgeDraft | None:
        return self._drafts.get(draft_id)

    async def list_drafts(self) -> list[KnowledgeDraft]:
        return [d for d in self._drafts.values() if d.status is DraftStatus.DRAFT]

    def _validate(self, content: KnowledgeContent, expert: str) -> None:
        if not expert.strip():
            raise ValidationError("expert_required")
        if not content.title.strip() or not content.solution.strip():
            raise ValidationError("missing_required_fields")  # a KB entry needs title + solution
        for article in self._current.values():
            same_title = _normalize(article.content.title) == _normalize(content.title)
            same_domain = (article.content.domain or "") == (content.domain or "")
            if same_title and same_domain:
                raise ValidationError("duplicate_article")

    async def approve(
        self, draft_id: str, *, expert: str, change_reason: str = ""
    ) -> KnowledgeArticle:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise ValidationError("draft_not_found")
        self._validate(draft.content, expert)
        self._seq += 1
        article_id = f"kb-learned-{self._seq:04d}"
        article = KnowledgeArticle(
            article_id=article_id,
            version=1,
            content=draft.content,
            approved_by=expert,
            change_reason=change_reason,
            gap_id=draft.gap_id,
        )
        self._versions[article_id] = [article]
        self._current[article_id] = article  # index refresh is immediate (in-memory)
        if self._embed is not None:
            self._vectors[article_id] = await self._embed(article.content.searchable_text())
        draft.status = DraftStatus.APPROVED
        return article

    async def reject(self, draft_id: str) -> KnowledgeDraft | None:
        draft = self._drafts.get(draft_id)
        if draft is not None:
            draft.status = DraftStatus.REJECTED
        return draft

    async def list_articles(self) -> list[KnowledgeArticle]:
        return list(self._current.values())

    async def _best(self, query: str) -> tuple[ArticleHit, str] | None:
        """The best current article for the query, with the scoring mode used.

        Semantic (cosine over content embeddings) when embeddings are configured, else
        lexical token overlap with a multi-word keyword bonus. Returns the hit and the
        mode so the caller applies the right floor.
        """
        if not self._current:
            return None
        if self._embed is not None and self._vectors:
            qv = await self._embed(query)
            best: ArticleHit | None = None
            for article in self._current.values():
                vec = self._vectors.get(article.article_id)
                if not vec:
                    continue
                sim = _cosine(qv, vec)
                if best is None or sim > best.score:
                    best = ArticleHit(article=article, score=sim)
            return (best, "semantic") if best is not None else None
        q = _tokens(query)
        if not q:
            return None
        norm_q = _normalize(query)
        best = None
        for article in self._current.values():
            terms = _tokens(article.content.searchable_text())
            score = float(len(q & terms))
            for kw in article.content.keywords + article.content.synonyms:
                nk = _normalize(kw)
                if " " in nk and nk in norm_q:
                    score += 2.0
            if best is None or score > best.score:
                best = ArticleHit(article=article, score=score)
        return (best, "lexical") if best is not None else None

    async def search(self, query: str) -> ArticleHit | None:
        """Best article at the normal floor - enough to answer from learned knowledge."""
        found = await self._best(query)
        if found is None:
            return None
        hit, mode = found
        return hit if hit.score >= self._NORMAL[mode] else None

    async def strong_match(self, query: str) -> ArticleHit | None:
        """Best article at the strong floor - enough to pre-empt a diagnostic tree."""
        found = await self._best(query)
        if found is None:
            return None
        hit, mode = found
        return hit if hit.score >= self._STRONG[mode] else None

    async def rollback(self, article_id: str, version: int) -> KnowledgeArticle | None:
        for article in self._versions.get(article_id, []):
            if article.version == version:
                self._current[article_id] = article
                return article
        return None
