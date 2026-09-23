"""Case reasoning state: the structured picture of one customer's situation.

The engine understands a free-form story, reconstructs it into typed facts, and
keeps that state across turns. A fact always carries its status - what the user
said (EXPLICIT), what was deduced (INFERRED), what is still missing (UNKNOWN) or
what a trusted source confirmed (VERIFIED) - so an inference is never mistaken
for a verified truth.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FactStatus(StrEnum):
    """Provenance of a fact; INFERRED must never be treated as VERIFIED."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    VERIFIED = "verified"


class CaseStatus(StrEnum):
    """Where the case is in the reasoning cycle."""

    UNDERSTANDING = "understanding"
    DIAGNOSING = "diagnosing"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    HANDOFF = "handoff"


class Fact(BaseModel):
    """One piece of the case with its provenance."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | None = None
    status: FactStatus
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "user"
    turn_id: int = 0


class CaseState(BaseModel):
    """The evolving structured case for one session."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    session_id: str
    domain: str | None = None
    user_goal: str | None = None
    problem_summary: str | None = None
    facts: dict[str, Fact] = Field(default_factory=dict)
    unknown_facts: list[str] = Field(default_factory=list)
    candidate_issues: list[str] = Field(default_factory=list)
    diagnosis: str | None = None
    diagnosis_confidence: float | None = None
    resolution_card_id: str | None = None
    status: CaseStatus = CaseStatus.UNDERSTANDING
    language: str = "uz"
    channel: str = "web"
    handoff_reason: str | None = None
    turn_count: int = 0

    def known_facts(self) -> dict[str, str]:
        """Return name -> value for facts that carry a real (non-unknown) value."""
        return {
            name: fact.value
            for name, fact in self.facts.items()
            if fact.value is not None and fact.status is not FactStatus.UNKNOWN
        }

    def has(self, name: str) -> bool:
        """True when the fact is known with a value (not merely marked unknown)."""
        fact = self.facts.get(name)
        return fact is not None and fact.value is not None and fact.status is not FactStatus.UNKNOWN

    def upsert(self, fact: Fact) -> None:
        """Add or update a fact, never downgrading a stronger status.

        A new INFERRED value does not overwrite an EXPLICIT or VERIFIED fact; any
        other update replaces the previous value (later turns win).
        """
        existing = self.facts.get(fact.name)
        if (
            existing is not None
            and existing.status in (FactStatus.EXPLICIT, FactStatus.VERIFIED)
            and fact.status is FactStatus.INFERRED
        ):
            return
        self.facts[fact.name] = fact
