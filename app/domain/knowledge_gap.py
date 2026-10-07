"""Knowledge gaps: questions the assistant could not answer from approved knowledge.

When retrieval finds no reliable evidence (or the grounded answer cannot be
authorised, or no tree/policy covers the issue), the assistant abstains - it must
never invent an answer. Instead of only logging "could not answer", it records a
structured KnowledgeGap with enough context for a domain expert to understand what is
actually missing: the question, the normalised form used for grouping, the
conversation context, what was searched and found, and why it failed.

Similar gaps are grouped (by normalised question) so an expert sees "27 users asked a
variation of this" and can supply the missing knowledge once. The gap then moves
through an expert review lifecycle (see :class:`GapStatus`) that ends in a versioned,
approved knowledge-base entry - never an unverified AI answer published on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GapStatus(StrEnum):
    """Where a knowledge gap is in the human-in-the-loop learning workflow."""

    NEW = "new"
    GROUPED = "grouped"
    NEEDS_EXPERT = "needs_expert"
    ANSWERED_BY_EXPERT = "answered_by_expert"
    DRAFT_CREATED = "draft_created"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"


class RetrievedDoc(BaseModel):
    """One document the retriever returned for the failed query, with its score."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    score: float


class KnowledgeGap(BaseModel):
    """A distinct missing-knowledge topic, with the context an expert needs.

    Occurrences of the same topic are merged into one record whose ``frequency`` and
    ``example_questions`` grow - so the dashboard shows how many users hit it, not one
    row per user. The message is stored already PII-redacted.
    """

    model_config = ConfigDict(extra="forbid")

    gap_id: str
    normalized_question: str
    question: str  # a representative (first) phrasing, PII-redacted
    example_questions: list[str] = Field(default_factory=list)
    domain: str | None = None
    intent: str | None = None
    conversation_context: str | None = None
    retrieval_queries: list[str] = Field(default_factory=list)
    retrieved_documents: list[RetrievedDoc] = Field(default_factory=list)
    reason_for_failure: str = ""  # no_evidence | weak_evidence | ungroundable | no_coverage
    assistant_uncertainty: float = 1.0
    frequency: int = 1
    status: GapStatus = GapStatus.NEW
    case_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC).isoformat()
