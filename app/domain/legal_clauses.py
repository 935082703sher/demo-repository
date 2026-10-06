"""The full VMQ-778 clause set, keyed by clause - the authoritative knowledge base.

Every substantive clause (1-50, its sub-clauses 6¹, 31¹, ... and the annexes) of the
regulation, in its current LexUZ revision, is stored as a :class:`Clause`: the clause
number, a faithful short paraphrase of its meaning, the subject it governs, retrieval
keywords (Uzbek + Russian), and the other clauses it relates to (the rule graph).

A clause is EVIDENCE for the reasoning engine, never a ready answer: the retriever
finds the clauses that fit a situation, the engine applies the specific over the
general, and the LLM synthesises a plain-language answer whose legal facts are
grounded in these clauses. The clause text here is a paraphrase for reasoning and
retrieval, not a verbatim quote to hand back to the customer.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Clause(BaseModel):
    """One distilled VMQ-778 clause with its subject, keywords and graph edges."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    source: str = "VMQ-778"
    clause: str
    display: str
    rule_type: str  # definition | requirement | responsibility | procedure | payment | ...
    subject: str
    legal_rule: str  # faithful paraphrase, not a verbatim quote
    keywords: list[str] = Field(default_factory=list)
    related_rules: list[str] = Field(default_factory=list)
    payment_ref: str | None = None
    deadline: str | None = None
    source_url: str = "https://lex.uz/docs/-4517458"


class ClauseBundle(BaseModel):
    """The full clause set loaded from the generated data file."""

    model_config = ConfigDict(extra="forbid")

    document: str = "VMQ-778"
    source_url: str = "https://lex.uz/docs/-4517458"
    revision_note: str = ""
    rules: list[Clause]

    @classmethod
    def from_json(cls, path: Path) -> ClauseBundle:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def by_clause(self) -> dict[str, Clause]:
        return {rule.clause: rule for rule in self.rules}
