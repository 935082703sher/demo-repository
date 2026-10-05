"""Decide whether a decision tree DIRECTLY covers a message - for every tree.

The decision tree is no longer a forced route; it is one evaluated candidate. This
evaluator classifies, for any message, how well the trees cover it:

- ``direct``  - a tree actually resolves this case (a specific sub-issue it declares
  in ``covers``, a strong keyword match, or a fact-complete card). Only ``direct``
  may enter a tree, and it enters the matched tree, never a generic root by default.
- ``partial`` - only the domain or a weak signal matched; no tree resolves it. The
  caller offers a topic menu instead of forcing a root question.
- ``none``    - the message names a specific sub-issue that NO tree covers. The
  caller must not fall into a generic tree; it searches the knowledge base and,
  with no grounded answer, recommends 1170 instead of inventing one.

Domain or keyword match alone is never ``direct`` for an uncovered specific issue -
that is the whole point of the gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.diagnostics import DecisionTree
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.fact_extraction import specific_issue


@dataclass(frozen=True)
class Coverage:
    """How the decision trees cover one message."""

    level: str  # "direct" | "partial" | "none"
    tree: DecisionTree | None
    issue: str | None
    domain_hint: str | None
    reason: str


class TreeCoverageEvaluator:
    """Evaluate tree coverage for a message, uniformly across all trees."""

    def __init__(self, engine: DiagnosticEngine) -> None:
        self._engine = engine

    def evaluate(
        self, message: str, *, domain: str | None, known_facts: dict[str, str]
    ) -> Coverage:
        # 1) A specific sub-issue must be handled by a tree that declares it.
        issue = specific_issue(message)
        if issue is not None:
            covering = self._engine.tree_covering(issue)
            if covering is not None:
                return Coverage("direct", covering, issue, covering.domain, f"covers:{issue}")
            return Coverage("none", None, issue, domain, f"uncovered:{issue}")

        # 2) A clear keyword winner directly covers the message.
        matched, route_domain = self._engine.route(message, domain=domain)
        if matched is not None:
            return Coverage("direct", matched, None, matched.domain, "keyword_match")

        # 3) Known facts may already complete a specific tree's card.
        from_facts = self._engine.tree_from_facts(known_facts, domain=domain)
        if from_facts is not None:
            return Coverage("direct", from_facts, None, from_facts.domain, "facts_match")

        # 4) Only a domain or nothing matched - offer a menu, never a forced root.
        return Coverage("partial", None, None, route_domain, "domain_or_none")
