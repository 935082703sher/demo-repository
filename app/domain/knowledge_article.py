"""Expert-approved knowledge: drafts and versioned, published articles.

A knowledge gap an expert answers becomes a structured :class:`KnowledgeDraft` - the
AI turns the expert's explanation into the fields a good KB entry needs, but it is
only a proposal. The expert reviews, edits, approves or rejects it. On approval the
draft becomes a :class:`KnowledgeArticle`: a versioned, attributed, verified entry
that the assistant may then retrieve and use. Nothing the AI writes reaches the
answerable knowledge base without that expert approval, and every version is kept so
a bad change can be rolled back.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class KnowledgeContent(BaseModel):
    """The substance of a KB entry - shared by a draft and a published article."""

    model_config = ConfigDict(extra="forbid")

    title: str
    domain: str | None = None
    intent: str | None = None
    problem: str = ""
    symptoms: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    diagnosis: str = ""
    solution: str = ""
    verification: str = ""
    exceptions: list[str] = Field(default_factory=list)
    when_to_route_operator: str = ""
    keywords: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    language_variants: dict[str, str] = Field(default_factory=dict)

    def searchable_text(self) -> str:
        """The text a retriever matches against (title, problem, keywords, synonyms)."""
        parts = [self.title, self.problem, self.solution, *self.keywords, *self.synonyms]
        return " ".join(p for p in parts if p)


class KnowledgeDraft(BaseModel):
    """A proposed KB entry awaiting expert review; never answerable on its own."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str
    gap_id: str | None = None
    content: KnowledgeContent
    source_expert: str = ""
    expert_answer: str = ""  # the raw expert explanation the draft was built from
    status: DraftStatus = DraftStatus.DRAFT
    created_at: str = Field(default_factory=_now)


class KnowledgeArticle(BaseModel):
    """A published, versioned, expert-approved KB entry the assistant may use."""

    model_config = ConfigDict(extra="forbid")

    article_id: str
    version: int
    content: KnowledgeContent
    approved_by: str
    source: str = "expert"
    change_reason: str = ""
    gap_id: str | None = None
    published_at: str = Field(default_factory=_now)
    superseded: bool = False
