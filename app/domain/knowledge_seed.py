"""The curated UZIMEI knowledge seed (v0.1): entries with an explicit trust status.

Every seed entry carries a status that decides how the assistant may use it:

- ``published_candidate`` - clear problem and outcome; usable in diagnostics;
- ``needs_current_verification`` - useful, but tied to a tariff, limit, law, agency
  or current procedure, so it is never stated as a firm fact until verified;
- ``needs_expert_input`` - the problem is known, the resolution steps are not;
- ``historical`` - an old transition-period rule, never active knowledge.

The seed also states the capability rule: the assistant cannot read live status from
UZIMEI, MNP, customs, operator or any other external system. It explains a status the
customer reports; it never pretends to have looked one up.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_seed.v0_1.json"


class SeedStatus(StrEnum):
    PUBLISHED_CANDIDATE = "published_candidate"
    NEEDS_CURRENT_VERIFICATION = "needs_current_verification"
    NEEDS_EXPERT_INPUT = "needs_expert_input"
    HISTORICAL = "historical"


class SeedEntry(BaseModel):
    """One curated knowledge entry and the rules that govern its use."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    domain: str
    title: str
    status: SeedStatus
    intents: list[str] = Field(default_factory=list)
    user_examples: list[str] = Field(default_factory=list)
    problem: str = ""
    possible_cause: str = ""
    required_facts: list[str] = Field(default_factory=list)
    status_codes: list[str] = Field(default_factory=list)
    diagnostic_flow: list[str] = Field(default_factory=list)
    resolution: str = ""
    exceptions: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    escalation: str = ""
    prerequisite: str = ""
    related: list[str] = Field(default_factory=list)
    security_level: str | None = None
    review_only: bool = False

    @property
    def usable_in_diagnostics(self) -> bool:
        """Only a published candidate may drive a diagnostic answer as-is."""
        return self.status is SeedStatus.PUBLISHED_CANDIDATE and not self.review_only

    @property
    def stated_as_fact(self) -> bool:
        """Whether the entry's content may be stated as a firm current fact."""
        return self.usable_in_diagnostics


class CapabilityRule(BaseModel):
    """What the assistant can and cannot do with live external-system status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    can_find_status: bool
    can_explain_status: bool
    can_analyse_problem: bool
    can_recommend_next_step: bool
    can_route_to_operator: bool
    forbidden_claims: list[str] = Field(default_factory=list)


class KnowledgeSeed(BaseModel):
    """The whole seed: status definitions, the capability rule and the entries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seed_version: str
    title: str
    language: str
    statuses: dict[SeedStatus, str]
    capability_rule: CapabilityRule
    entries: list[SeedEntry]

    def get(self, entry_id: str) -> SeedEntry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def by_status_code(self, code: str) -> SeedEntry | None:
        """The entry that explains an official status code the customer reported."""
        return next((e for e in self.entries if code in e.status_codes), None)


@lru_cache(maxsize=1)
def load_seed(path: Path = _SEED_PATH) -> KnowledgeSeed:
    """Load and validate the seed (cached; the file is read-only at runtime)."""
    return KnowledgeSeed.model_validate(json.loads(path.read_text(encoding="utf-8")))
