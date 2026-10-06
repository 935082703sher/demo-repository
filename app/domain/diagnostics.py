"""Typed models for the diagnostic decision trees and resolution cards.

A decision tree is deterministic business logic: each node asks one question and
each answer points either to the next node or to a resolution card. Facts are
never stored here - a card links to knowledge-base sources by ``kb_refs`` (doc
ids) so the answer layer can cite the approved fact.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RiskLevel(StrEnum):
    """How cautious a resolution's steps are; gates what may be auto-offered."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LocalizedText(_Model):
    """One string in the supported languages; uz is the fallback."""

    uz: str = Field(min_length=1)
    ru: str = Field(min_length=1)
    en: str | None = None

    def get(self, language: str) -> str:
        return {"uz": self.uz, "ru": self.ru, "en": self.en}.get(language) or self.uz


class SuccessCheck(_Model):
    """How to tell, from the customer's next reply, whether a card worked.

    The signals are lowercase keyword hints for the deterministic fallback; the
    LLM outcome analyzer reads the reply directly. Either may decide the outcome.
    """

    question: LocalizedText | None = None
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)


class OutcomeBranch(_Model):
    """Where the lifecycle goes after one outcome of a card.

    ``status`` sets a terminal CaseStatus value (e.g. "resolved"); ``next_node``
    or ``next_card`` continues diagnosis; ``request_evidence`` asks the customer
    for the exact on-screen or SMS error text. All optional and backward-safe.
    """

    status: str | None = None
    next_node: str | None = None
    next_card: str | None = None
    request_evidence: bool = False


class DiagnosticOption(_Model):
    """One selectable answer to a node's question."""

    value: str = Field(min_length=1)
    label: LocalizedText
    next_node: str | None = None
    card: str | None = None
    fact_value: str | None = None  # the CaseState fact value this option represents


class DiagnosticNode(_Model):
    """One diagnostic question with its branches."""

    id: str = Field(min_length=1)
    question: LocalizedText
    fact: str | None = None  # the case fact this node establishes (for auto-advance)
    options: list[DiagnosticOption] = Field(min_length=1)


class DecisionTree(_Model):
    """A per-case decision tree rooted at ``root``.

    ``covers`` lists the specific sub-issues this tree actually resolves (e.g.
    "secondary_imei_registration"). The coverage gate enters a tree for such an
    issue only when the tree declares it, so a mere domain/keyword match never
    pulls a specific problem into a generic tree's root.
    """

    id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    case_type: str = Field(min_length=1)
    title: LocalizedText
    keywords: list[str] = Field(default_factory=list)
    covers: list[str] = Field(default_factory=list)
    root: str = Field(min_length=1)
    nodes: list[DiagnosticNode] = Field(min_length=1)


class ResolutionCard(_Model):
    """An approved, structured resolution for one diagnostic outcome.

    The base fields (title, probable_cause, steps, ...) are unchanged. The
    lifecycle fields below are all optional, so existing cards keep validating:
    when a card defines ``success_check`` and outcome branches, the resolution
    orchestrator can follow success/failure/partial/unclear paths; otherwise the
    card behaves exactly as before (a one-shot answer).
    """

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
    # The VMQ-778 PolicyRule ids this resolution is grounded in. They bind the tree
    # outcome to the authoritative law: the matched subset becomes the legal basis
    # for the final answer and is recorded in the trace/audit. Empty when the card is
    # not governed by VMQ-778 (e.g. MNP cards).
    policy_rule_ids: list[str] = Field(default_factory=list)
    # Resolution lifecycle (all optional, backward-compatible).
    risk: RiskLevel = RiskLevel.LOW
    cause_key: str | None = None  # stable id of the probable cause, for exclusion
    success_check: SuccessCheck | None = None
    on_success: OutcomeBranch | None = None
    on_failure: OutcomeBranch | None = None
    on_partial: OutcomeBranch | None = None
    on_unclear: OutcomeBranch | None = None
    request_evidence: bool = False
    stop_conditions: list[str] = Field(default_factory=list)
    call_1170_when: list[str] = Field(default_factory=list)


class DiagnosticBundle(_Model):
    """The full set of trees and cards loaded from the fixture."""

    trees: list[DecisionTree]
    cards: list[ResolutionCard]
