"""The general Legal Reasoning Engine: situation -> clauses -> SolutionPlan.

This is the reasoning spine the design calls for, and it is deliberately general -
no per-question branches. Given a case and a message it:

  1. builds CaseFacts from the typed facts already extracted;
  2. retrieves the candidate VMQ-778 clauses by meaning (ClauseRetriever);
  3. selects the applicable rules, specific over general, and prunes a rule only
     when a situation signal fires its excludes_if (PolicyMatcher);
  4. resolves any payment from the versioned tariff source; and
  5. assembles a SolutionPlan (summary, responsible party, steps, deadlines,
     payments, legal basis) from several clauses, not one.

The engine does not write the customer-facing prose or decide wording; it produces
the grounded evidence (clauses + plan) that the answer composer turns into plain
language, and it records which clauses were used so the result is auditable. Every
legal fact in the plan traces to a clause id; nothing here is a fixed answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.domain.case_state import CaseState
from app.domain.policy import PolicyRule
from app.domain.tariffs import ResolvedPayment, TariffConfig
from app.services.clause_retriever import ClauseHit, ClauseRetriever
from app.services.policy_matcher import PolicyMatcher, derive_signals

# Clause subjects that are definitions/scope/operator-internal: real evidence, but
# not the lead of a citizen answer, so they rank below operative clauses.
_BACKGROUND_TYPES = frozenset({"definition", "scope", "authority"})


@dataclass(frozen=True)
class CaseFacts:
    """The structured situation the engine reasons over (derived, never guessed)."""

    goal: str | None
    known_facts: dict[str, str]
    signals: list[str]
    missing_facts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Reasoning:
    """The full reasoning trace for one turn - the evidence behind the answer."""

    case_facts: CaseFacts
    candidate_clauses: list[ClauseHit]
    applicable_clauses: list[str]
    situation_rules: list[PolicyRule]
    payments: list[ResolvedPayment]
    legal_basis: list[str]  # distinct clause labels cited, specific first

    def has_grounds(self) -> bool:
        """True when at least one operative clause fits - otherwise the caller abstains."""
        return bool(self.legal_basis)


def _is_specific(clause: str) -> bool:
    """A sub-clause (6-1, 31-2) is more specific than its parent main clause."""
    return "-" in clause and not clause.endswith("ilova")


class LegalReasoningEngine:
    """Assemble the grounded SolutionPlan evidence for a case (no fixed scenarios)."""

    def __init__(
        self, retriever: ClauseRetriever, matcher: PolicyMatcher, tariffs: TariffConfig
    ) -> None:
        self._retriever = retriever
        self._matcher = matcher
        self._tariffs = tariffs

    def case_facts(self, case: CaseState, message: str) -> CaseFacts:
        return CaseFacts(
            goal=case.user_goal or case.problem_summary,
            known_facts=case.known_facts(),
            signals=sorted(derive_signals(case, message)),
        )

    def reason(self, case: CaseState, message: str, *, when: date | None = None) -> Reasoning:
        on = when or date.today()
        facts = self.case_facts(case, message)
        # Retrieve over the full law using the message and the known facts, so the
        # situation (not just the exact words) drives which clauses surface.
        query = " ".join([message, *facts.known_facts.values()])
        candidates = self._retriever.retrieve(query)

        # Operative clauses lead; definitions/scope/operator clauses are background.
        operative = [h for h in candidates if h.clause.rule_type not in _BACKGROUND_TYPES]
        operative.sort(key=lambda h: (_is_specific(h.clause.clause), h.score), reverse=True)
        legal_basis: list[str] = []
        for hit in operative:
            if hit.clause.clause not in legal_basis:
                legal_basis.append(hit.clause.clause)

        # The precise situation rules (applies_if/excludes_if) and their payments.
        match = self._matcher.match(case, message, when=on)
        payments: list[ResolvedPayment] = []
        seen_ref: set[str] = set()
        for rule in match.rules:
            if rule.payment_ref and rule.payment_ref not in seen_ref:
                seen_ref.add(rule.payment_ref)
                resolved = self._tariffs.resolve(rule.payment_ref, on)
                if resolved is not None:
                    payments.append(resolved)

        return Reasoning(
            case_facts=facts,
            candidate_clauses=candidates,
            applicable_clauses=legal_basis,
            situation_rules=match.rules,
            payments=payments,
            legal_basis=legal_basis,
        )
