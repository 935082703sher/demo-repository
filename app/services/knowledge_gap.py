"""Record and group knowledge gaps for the expert learning workflow.

The store deduplicates: a new gap whose normalised question matches an existing one
(exactly, or by strong token overlap) merges into it - bumping ``frequency`` and
adding the phrasing and case id - instead of creating a second row. So the expert
dashboard shows distinct missing-knowledge topics with how often each is hit, and an
expert can resolve one topic rather than answering every case.

Recording never breaks a turn: it is additive and best-effort. The default store is
in-memory (dev/tests); a persistent implementation can be swapped in behind the same
protocol, mirroring the case/audit stores.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.knowledge_gap import GapStatus, KnowledgeGap, RetrievedDoc
from app.services.fact_extraction import _normalize


def _tokens(normalized: str) -> set[str]:
    return {t for t in normalized.split() if len(t) > 2}


def _similar(a: str, b: str) -> bool:
    """True when two normalised questions are the same topic (token Jaccard >= 0.5).

    A lexical grouper for near-duplicate phrasings; the expert still reviews each
    topic. Semantically distant variants ("4G yo'q" vs "internet ishlamayapti") are a
    known limitation here - embeddings would group those, see the report.
    """
    if a == b:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / len(ta | tb)
    return overlap >= 0.5


@runtime_checkable
class KnowledgeGapStore(Protocol):
    """Sink and query surface for knowledge gaps."""

    async def record(
        self,
        *,
        question: str,
        domain: str | None,
        intent: str | None,
        reason: str,
        conversation_context: str | None = None,
        retrieval_queries: list[str] | None = None,
        retrieved_documents: list[RetrievedDoc] | None = None,
        assistant_uncertainty: float = 1.0,
        case_id: str | None = None,
    ) -> KnowledgeGap: ...

    async def list(self, *, status: GapStatus | None = None) -> list[KnowledgeGap]: ...

    async def get(self, gap_id: str) -> KnowledgeGap | None: ...

    async def set_status(self, gap_id: str, status: GapStatus) -> KnowledgeGap | None: ...


class NullKnowledgeGapStore:
    """No-op store (used where gap capture is disabled)."""

    async def record(
        self,
        *,
        question: str,
        domain: str | None,
        intent: str | None,
        reason: str,
        conversation_context: str | None = None,
        retrieval_queries: list[str] | None = None,
        retrieved_documents: list[RetrievedDoc] | None = None,
        assistant_uncertainty: float = 1.0,
        case_id: str | None = None,
    ) -> KnowledgeGap:
        return KnowledgeGap(gap_id="null", normalized_question="", question="")

    async def list(self, *, status: GapStatus | None = None) -> list[KnowledgeGap]:
        return []

    async def get(self, gap_id: str) -> KnowledgeGap | None:
        return None

    async def set_status(self, gap_id: str, status: GapStatus) -> KnowledgeGap | None:
        return None


class InMemoryKnowledgeGapStore:
    """In-memory gap store with normalised-question grouping (dev/tests)."""

    def __init__(self) -> None:
        self._gaps: dict[str, KnowledgeGap] = {}
        self._seq = 0

    async def record(
        self,
        *,
        question: str,
        domain: str | None,
        intent: str | None,
        reason: str,
        conversation_context: str | None = None,
        retrieval_queries: list[str] | None = None,
        retrieved_documents: list[RetrievedDoc] | None = None,
        assistant_uncertainty: float = 1.0,
        case_id: str | None = None,
    ) -> KnowledgeGap:
        normalized = _normalize(question)
        existing = self._find_similar(normalized)
        if existing is not None:
            existing.frequency += 1
            if question not in existing.example_questions:
                existing.example_questions.append(question)
            if case_id and case_id not in existing.case_ids:
                existing.case_ids.append(case_id)
            if existing.status is GapStatus.NEW and existing.frequency >= 2:
                existing.status = GapStatus.GROUPED
            existing.touch()
            return existing

        self._seq += 1
        gap = KnowledgeGap(
            gap_id=f"gap-{self._seq:04d}",
            normalized_question=normalized,
            question=question,
            example_questions=[question],
            domain=domain,
            intent=intent,
            conversation_context=conversation_context,
            retrieval_queries=retrieval_queries or [],
            retrieved_documents=retrieved_documents or [],
            reason_for_failure=reason,
            assistant_uncertainty=assistant_uncertainty,
            case_ids=[case_id] if case_id else [],
        )
        self._gaps[gap.gap_id] = gap
        return gap

    def _find_similar(self, normalized: str) -> KnowledgeGap | None:
        for gap in self._gaps.values():
            if _similar(gap.normalized_question, normalized):
                return gap
        return None

    async def list(self, *, status: GapStatus | None = None) -> list[KnowledgeGap]:
        gaps = [g for g in self._gaps.values() if status is None or g.status is status]
        return sorted(gaps, key=lambda g: (g.frequency, g.updated_at), reverse=True)

    async def get(self, gap_id: str) -> KnowledgeGap | None:
        return self._gaps.get(gap_id)

    async def set_status(self, gap_id: str, status: GapStatus) -> KnowledgeGap | None:
        gap = self._gaps.get(gap_id)
        if gap is not None:
            gap.status = status
            gap.touch()
        return gap
