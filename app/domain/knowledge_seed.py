"""The curated UZIMEI & MNP knowledge base (v1.0): articles with an explicit trust status.

Every article carries a status that decides how the assistant may use it:

- ``published_candidate`` - the source is clear; usable in an answer;
- ``needs_current_verification`` - a tariff, deadline, state procedure or other
  time-bound value, never stated as a firm fact until verified against the current
  regulation (time-sensitive values also carry versioned ``policy`` metadata);
- ``needs_expert_input`` - the problem is known, the practical details are not;
- ``historical`` - an old transition-period rule, never used for ordinary questions.

The knowledge base also states the capability rule: the assistant cannot read live
status from UZIMEI, MNP, customs, operator or any other external system. It explains
a status the customer reports, and tells them the official way to check it; it never
pretends to have looked one up.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_KB_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.v1_0.json"


class SeedStatus(StrEnum):
    PUBLISHED_CANDIDATE = "published_candidate"
    NEEDS_CURRENT_VERIFICATION = "needs_current_verification"
    NEEDS_EXPERT_INPUT = "needs_expert_input"
    HISTORICAL = "historical"


class PolicyMetadata(BaseModel):
    """Versioning for a time-sensitive value (tariff, deadline, limit, channel list)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_type: str
    effective_from: str | None = None
    effective_to: str | None = None
    requires_current_verification: bool
    expert_reviewed: bool


class SeedEntry(BaseModel):
    """One curated knowledge article and the rules that govern its use."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    domain: str
    topic: str
    intent: list[str] = Field(default_factory=list)
    status: SeedStatus
    risk_level: str = "normal"
    requires_realtime_status: bool = False
    requires_identity: bool = False
    requires_current_policy_check: bool = False
    user_examples: list[str] = Field(default_factory=list)
    answer: str = ""
    symptoms: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    resolution_steps: list[str] = Field(default_factory=list)
    diagnostic_questions: list[str] = Field(default_factory=list)
    assistant_must_not: list[str] = Field(default_factory=list)
    status_codes: list[str] = Field(default_factory=list)
    source_type: str
    version: int
    note: str = ""
    carried_from: str | None = None
    policy: PolicyMetadata | None = None

    @property
    def usable_in_diagnostics(self) -> bool:
        """Only a published candidate may drive an answer as-is."""
        return self.status is SeedStatus.PUBLISHED_CANDIDATE

    @property
    def stated_as_fact(self) -> bool:
        """Whether the article's content may be stated as a firm current fact."""
        return self.usable_in_diagnostics and not (
            self.policy is not None and self.policy.requires_current_verification
        )

    def index_text(self) -> str:
        """The answerable text a retriever indexes: title, answer and steps."""
        steps = " ".join(f"{i}) {s}" for i, s in enumerate(self.resolution_steps, 1))
        parts = [self.title, self.answer, f"Qadamlar: {steps}" if steps else ""]
        return "\n".join(p for p in parts if p)


class CapabilityRule(BaseModel):
    """What the assistant can and cannot do with live external-system status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    can_find_status: bool
    can_explain_status: bool
    can_analyse_problem: bool
    can_recommend_next_step: bool
    can_route_to_operator: bool
    official_check_methods: dict[str, list[str]] = Field(default_factory=dict)
    forbidden_claims: list[str] = Field(default_factory=list)


class ConversationRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    rule: str


class RetrievalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index_statuses: list[SeedStatus]
    exclude_from_index: list[SeedStatus]
    flow: list[str]
    principle: dict[str, str]


class SourceConflict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic: str
    removed_rule: str
    replacement: str
    reason: str
    see: str


class KnowledgeSeed(BaseModel):
    """The whole knowledge base: statuses, rules, policies and the articles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kb_version: str
    title: str
    language: str
    statuses: dict[SeedStatus, str]
    capability_rule: CapabilityRule
    conversation_rules: list[ConversationRule]
    retrieval_policy: RetrievalPolicy
    time_sensitive_topics: list[str]
    excluded_data: list[str]
    source_conflicts: list[SourceConflict]
    superseded_v0_1: dict[str, str]
    articles: list[SeedEntry]

    def get(self, article_id: str) -> SeedEntry | None:
        return next((a for a in self.articles if a.id == article_id), None)

    def by_status_code(self, code: str) -> SeedEntry | None:
        """The article that explains an official status code the customer reported."""
        return next((a for a in self.articles if code in a.status_codes), None)

    def indexable(self) -> list[SeedEntry]:
        """Articles the retrieval policy allows into the answerable index."""
        allowed = set(self.retrieval_policy.index_statuses)
        return [a for a in self.articles if a.status in allowed and a.answer]


@lru_cache(maxsize=1)
def load_seed(path: Path = _KB_PATH) -> KnowledgeSeed:
    """Load and validate the knowledge base (cached; read-only at runtime)."""
    return KnowledgeSeed.model_validate(json.loads(path.read_text(encoding="utf-8")))
