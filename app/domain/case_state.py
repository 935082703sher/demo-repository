"""Case reasoning state: the structured picture of one customer's situation.

The engine understands a free-form story, reconstructs it into typed facts, and
keeps that state across turns. A fact always carries its status - what the user
said (EXPLICIT), what was deduced (INFERRED), what is still missing (UNKNOWN) or
what a trusted source confirmed (VERIFIED) - so an inference is never mistaken
for a verified truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FactStatus(StrEnum):
    """Provenance of a fact; INFERRED must never be treated as VERIFIED."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    VERIFIED = "verified"


class CaseStatus(StrEnum):
    """Where the case is in the reasoning cycle.

    The resolution lifecycle runs DIAGNOSING -> WAITING_FOR_RESULT (a card was
    offered, now its result is awaited) -> TRYING_ALTERNATIVE (that card did not
    resolve it, another safe path is being tried) -> RESOLVED, or, when every safe
    path is exhausted, CALL_1170_RECOMMENDED. UNDERSTANDING/RESOLVING/HANDOFF are
    kept for backward compatibility with the earlier flow.
    """

    UNDERSTANDING = "understanding"
    DIAGNOSING = "diagnosing"
    RESOLVING = "resolving"
    WAITING_FOR_RESULT = "waiting_for_result"
    TRYING_ALTERNATIVE = "trying_alternative"
    RESOLVED = "resolved"
    CALL_1170_RECOMMENDED = "call_1170_recommended"
    HANDOFF = "handoff"


class Outcome(StrEnum):
    """How a customer's reply to an offered resolution turned out.

    UNCLEAR is never a FAILURE: it means the reply did not say whether the step
    worked (e.g. "I don't understand"), so the assistant clarifies rather than
    discarding the card.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    UNCLEAR = "unclear"


class ExplanationStyle(StrEnum):
    """How the same approved resolution is explained; facts never change."""

    CONCISE = "concise"
    SIMPLE = "simple"
    STEP_BY_STEP = "step_by_step"
    EXAMPLE = "example"
    DETAILED = "detailed"
    TECHNICAL = "technical"
    VISUAL = "visual"
    REASSURING = "reassuring"


class ResolutionAttempt(BaseModel):
    """One offered resolution and what came of it, so it is never repeated blindly."""

    model_config = ConfigDict(extra="forbid")

    card_id: str
    step: str | None = None
    outcome: Outcome | None = None
    new_facts: list[str] = Field(default_factory=list)
    evidence: str | None = None
    next_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExplanationProfile(BaseModel):
    """How this customer prefers the resolution explained (adapts, never the facts)."""

    model_config = ConfigDict(extra="forbid")

    language: str = "uz"
    style: ExplanationStyle = ExplanationStyle.SIMPLE
    technical_level: str = "beginner"
    preferred_length: str = "short"
    needs_examples: bool = False
    confusion_count: int = 0


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
    active_tree: str | None = None
    pending_node: str | None = None
    status: CaseStatus = CaseStatus.UNDERSTANDING
    language: str = "uz"
    channel: str = "web"
    handoff_reason: str | None = None
    turn_count: int = 0
    # Resolution lifecycle: what has been tried, what is left, and why.
    current_cause: str | None = None
    excluded_causes: list[str] = Field(default_factory=list)
    remaining_causes: list[str] = Field(default_factory=list)
    tried_card_ids: list[str] = Field(default_factory=list)
    attempts: list[ResolutionAttempt] = Field(default_factory=list)
    last_question: str | None = None
    last_customer_reply: str | None = None
    call_1170_reason: str | None = None
    explanation: ExplanationProfile = Field(default_factory=ExplanationProfile)
    # Conversation state: the first problem (kept so a menu rejection re-examines it)
    # and whether the previous turn offered a topic menu awaiting a selection.
    original_problem: str | None = None
    awaiting_menu: bool = False

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

    def card_tried(self, card_id: str) -> bool:
        """True when this resolution card has already been offered in this case."""
        return card_id in self.tried_card_ids

    def record_attempt(self, attempt: ResolutionAttempt) -> None:
        """Log an offered resolution so it is never repeated without a reason."""
        self.attempts.append(attempt)
        if attempt.card_id not in self.tried_card_ids:
            self.tried_card_ids.append(attempt.card_id)

    def exclude_cause(self, cause: str) -> None:
        """Rule out a probable cause a failed attempt disproved; keep the rest."""
        if cause and cause not in self.excluded_causes:
            self.excluded_causes.append(cause)
        self.remaining_causes = [c for c in self.remaining_causes if c != cause]
