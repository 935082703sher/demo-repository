"""Typed models for the diagnostic decision trees and resolution cards.

A decision tree is deterministic business logic: each node asks one question and
each answer points either to the next node or to a resolution card. Facts are
never stored here - a card links to knowledge-base sources by ``kb_refs`` (doc
ids) so the answer layer can cite the approved fact.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalizedText(_Model):
    """One string in the supported languages; uz is the fallback."""

    uz: str = Field(min_length=1)
    ru: str = Field(min_length=1)
    en: str | None = None

    def get(self, language: str) -> str:
        return {"uz": self.uz, "ru": self.ru, "en": self.en}.get(language) or self.uz


class DiagnosticOption(_Model):
    """One selectable answer to a node's question."""

    value: str = Field(min_length=1)
    label: LocalizedText
    next_node: str | None = None
    card: str | None = None


class DiagnosticNode(_Model):
    """One diagnostic question with its branches."""

    id: str = Field(min_length=1)
    question: LocalizedText
    options: list[DiagnosticOption] = Field(min_length=1)


class DecisionTree(_Model):
    """A per-case decision tree rooted at ``root``."""

    id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    case_type: str = Field(min_length=1)
    title: LocalizedText
    keywords: list[str] = Field(default_factory=list)
    root: str = Field(min_length=1)
    nodes: list[DiagnosticNode] = Field(min_length=1)


class ResolutionCard(_Model):
    """An approved, structured resolution for one diagnostic outcome."""

    id: str = Field(min_length=1)
    title: LocalizedText
    probable_cause: LocalizedText
    steps: list[LocalizedText] = Field(min_length=1)
    documents: list[LocalizedText] = Field(default_factory=list)
    where_to_apply: LocalizedText | None = None
    official_url: str | None = None
    contact: str | None = None
    escalate_when: LocalizedText | None = None
    kb_refs: list[str] = Field(default_factory=list)


class DiagnosticBundle(_Model):
    """The full set of trees and cards loaded from the fixture."""

    trees: list[DecisionTree]
    cards: list[ResolutionCard]
