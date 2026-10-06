"""Structured legal rules distilled from an authoritative policy source.

VMQ-778 (Cabinet of Ministers resolution of 17.09.2019, in its current LexUZ
revision) is the authoritative source of *what is true* - who must register a
device, when registration is required, which rules apply to residents and
non-residents, the payment formula, and when a device cannot be registered. It is
NOT a set of ready answers: the raw text is never returned to a customer verbatim.

Each substantive clause is distilled into a :class:`PolicyRule` - a fact with its
provenance (document, clause, source URL, effective dates) and the conditions under
which it applies (``applies_if`` / ``excludes_if``). The matcher selects the rules
that fit the customer's situation; the LLM then applies and explains them in natural
language, and a grounding check confirms every legal claim carries a clause and
source. The LLM may never change a legal fact, only apply and phrase it.

Monetary amounts are deliberately kept as a *formula* (a percentage of the BHM, the
base calculation unit) rather than a hardcoded sum: the current BHM value comes from
a versioned tariff source (:mod:`app.domain.tariffs`), so a BHM change never requires
touching a rule or the code.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class PolicyRule(BaseModel):
    """One distilled legal rule, with full provenance and applicability conditions."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    source_type: str = "law"
    authority: str = "LexUZ"
    document: str = "VMQ-778"
    clause: str
    effective_from: date
    effective_to: date | None = None
    jurisdiction: str = "UZ"
    topic: str
    # Controlled situation signals: a rule applies when every ``applies_if`` signal is
    # present and no ``excludes_if`` signal is. An empty ``applies_if`` is a general
    # rule for its topic. Signals come from the derived case situation, never raw text.
    applies_if: list[str] = Field(default_factory=list)
    excludes_if: list[str] = Field(default_factory=list)
    # The exact legal meaning, paraphrased from the source - the ground truth the LLM
    # must apply unchanged. Kept short; it is evidence, not the customer-facing answer.
    legal_rule: str
    required_evidence: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    escalation_conditions: list[str] = Field(default_factory=list)
    # A payment formula reference (e.g. "physical_person_within_30_days"), resolved to
    # a current amount by the tariff source. None when the rule carries no payment.
    payment_ref: str | None = None
    source_url: str = "https://lex.uz/docs/-4517458"

    def is_effective_on(self, when: date) -> bool:
        """True when the rule is in force on the given date."""
        if when < self.effective_from:
            return False
        return self.effective_to is None or when <= self.effective_to

    def matches(self, signals: set[str]) -> bool:
        """True when every applies_if signal holds and no excludes_if signal does."""
        if any(signal in signals for signal in self.excludes_if):
            return False
        return all(signal in signals for signal in self.applies_if)

    def specificity(self) -> int:
        """How many conditions a rule carries; more specific rules rank first."""
        return len(self.applies_if) + len(self.excludes_if)


class PolicyBundle(BaseModel):
    """The full set of distilled policy rules, loaded from the data file."""

    model_config = ConfigDict(extra="forbid")

    source: str = "VMQ-778"
    source_url: str = "https://lex.uz/docs/-4517458"
    rules: list[PolicyRule]
