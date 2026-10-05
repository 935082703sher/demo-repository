"""Drive one case through the resolution lifecycle.

The decision engine still decides WHICH card fits a diagnosis; this orchestrator
decides WHAT HAPPENS AFTER a card is offered. It offers a card, waits for the
result, and on the next reply's classified outcome it either closes the case,
tries the next safe untried card, continues diagnosis, asks for evidence, or - only
once every safe path is exhausted - recommends calling 1170. It never invents a
step or a fact and never closes a case the customer did not confirm; it only moves
between the CaseStatus states and records every attempt so none is repeated blindly.

Only cards that define a ``success_check`` enter this loop; a plain card stays a
one-shot answer, so existing behaviour is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.case_state import CaseState, CaseStatus, Outcome, ResolutionAttempt
from app.domain.diagnostics import DiagnosticNode, ResolutionCard, RiskLevel
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.outcome_analyzer import OutcomeAnalysis

# Cards above this risk are never auto-offered as a fallback alternative; a risky
# step is only reached through its own curated branch, never by exhaustion search.
_AUTO_OFFER_RISK = {RiskLevel.LOW, RiskLevel.MEDIUM}

CALL_1170_EXHAUSTED = "all_safe_paths_exhausted"
CALL_1170_REQUESTED = "customer_requested_phone"

# A case in either state is waiting for the customer's result on an offered card,
# so the next message is a result to classify, not a fresh problem.
AWAITING_OUTCOME = frozenset({CaseStatus.WAITING_FOR_RESULT, CaseStatus.TRYING_ALTERNATIVE})


@dataclass(frozen=True)
class OrchestratorDecision:
    """What the conversation layer should do next for this case."""

    kind: (
        str  # offer_card | ask_node | request_evidence | reexplain | clarify | resolved | call_1170
    )
    card: ResolutionCard | None = None
    node: DiagnosticNode | None = None
    reason: str = ""


class ResolutionOrchestrator:
    """Lifecycle controller over CaseState, the engine, and a classified outcome."""

    def __init__(self, engine: DiagnosticEngine) -> None:
        self._engine = engine

    def uses_lifecycle(self, card: ResolutionCard) -> bool:
        """A card joins the result-tracking loop only if it says how to check success."""
        return card.success_check is not None

    def offer_card(
        self,
        case: CaseState,
        card: ResolutionCard,
        *,
        status: CaseStatus = CaseStatus.WAITING_FOR_RESULT,
    ) -> OrchestratorDecision:
        """Offer a card and wait for its result; records it so it is never repeated.

        ``status`` is WAITING_FOR_RESULT for a first offer and TRYING_ALTERNATIVE
        when this card follows a failed one; both mean the next reply is a result.
        """
        case.resolution_card_id = card.id
        case.current_cause = card.cause_key or card.id
        case.status = status
        case.record_attempt(ResolutionAttempt(card_id=card.id))
        return OrchestratorDecision(kind="offer_card", card=card)

    def advance(self, case: CaseState, outcome: OutcomeAnalysis) -> OrchestratorDecision:
        """Transition the case from the offered card given the classified outcome."""
        card = self._engine.get_card(case.resolution_card_id or "")
        if card is None:  # nothing to track -> ask again rather than guess
            return OrchestratorDecision(kind="clarify", reason="no_active_card")
        case.record_attempt(
            ResolutionAttempt(
                card_id=card.id,
                outcome=outcome.outcome,
                new_facts=[f.name for f in outcome.extracted_facts],
                next_path=outcome.outcome.value,
            )
        )

        if outcome.outcome is Outcome.SUCCESS:
            case.status = CaseStatus.RESOLVED
            return OrchestratorDecision(kind="resolved", card=card)

        if outcome.outcome is Outcome.UNCLEAR:
            # Never discard the card on "I don't understand"; ask or re-explain.
            if (card.on_unclear and card.on_unclear.request_evidence) or card.request_evidence:
                return OrchestratorDecision(kind="request_evidence", card=card)
            case.explanation.confusion_count += 1
            return OrchestratorDecision(kind="reexplain", card=card)

        if outcome.outcome is Outcome.PARTIAL:
            branch = card.on_partial
            node = self._node(case.active_tree, branch.next_node) if branch else None
            if node is not None:
                case.status = CaseStatus.DIAGNOSING
                case.pending_node = node.id
                return OrchestratorDecision(kind="ask_node", node=node)
            nxt = self._branch_card(branch.next_card if branch else None, case)
            if nxt is not None:
                return self.offer_card(case, nxt)
            case.status = CaseStatus.DIAGNOSING
            return OrchestratorDecision(kind="clarify", reason="partial_remaining")

        # FAILURE: rule out this cause, then take the next safe path.
        case.exclude_cause(case.current_cause or card.cause_key or card.id)
        branch = card.on_failure
        if branch is not None and branch.status == "call_1170":
            # The card declares no safe alternative: recommend 1170 without searching
            # the tree for an unrelated sibling card.
            return self.recommend_1170(case, CALL_1170_EXHAUSTED)
        nxt = self._branch_card(branch.next_card if branch else None, case)
        if nxt is not None:
            return self.offer_card(case, nxt, status=CaseStatus.TRYING_ALTERNATIVE)
        node = self._node(case.active_tree, branch.next_node) if branch else None
        if node is not None:
            case.status = CaseStatus.DIAGNOSING
            case.pending_node = node.id
            return OrchestratorDecision(kind="ask_node", node=node)
        alt = self._next_untried_card(case)
        if alt is not None:
            return self.offer_card(case, alt, status=CaseStatus.TRYING_ALTERNATIVE)
        return self.recommend_1170(case, CALL_1170_EXHAUSTED)

    def recommend_1170(self, case: CaseState, reason: str) -> OrchestratorDecision:
        """Final fallback once safe paths are exhausted; keeps the attempt history."""
        case.status = CaseStatus.CALL_1170_RECOMMENDED
        case.call_1170_reason = reason
        case.resolution_card_id = None
        return OrchestratorDecision(kind="call_1170", reason=reason)

    def _node(self, tree_id: str | None, node_id: str | None) -> DiagnosticNode | None:
        if not tree_id or not node_id:
            return None
        return self._engine.get_node(tree_id, node_id)

    def _branch_card(self, card_id: str | None, case: CaseState) -> ResolutionCard | None:
        if not card_id:
            return None
        card = self._engine.get_card(card_id)
        if card is None or case.card_tried(card.id):
            return None
        return card

    def _next_untried_card(self, case: CaseState) -> ResolutionCard | None:
        """First safe, untried card reachable in the active tree, else None."""
        tree = self._engine.get_tree(case.active_tree or "")
        if tree is None:
            return None
        for node in tree.nodes:
            for option in node.options:
                if option.card is None or case.card_tried(option.card):
                    continue
                card = self._engine.get_card(option.card)
                if card is None or card.risk not in _AUTO_OFFER_RISK:
                    continue
                if card.cause_key and card.cause_key in case.excluded_causes:
                    continue
                return card
        return None
