"""Deterministic diagnostic decision-tree engine.

Loads the trees and resolution cards, checks their integrity at startup, matches
a free-text problem to a tree, and advances one step at a time: given the current
node and the chosen answer it returns either the next question or a resolution
card. It holds no facts - a card links to knowledge-base sources by ``kb_refs``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.domain.diagnostics import (
    DecisionTree,
    DiagnosticBundle,
    DiagnosticNode,
    ResolutionCard,
)

_TOKEN = re.compile(r"[a-z0-9]{3,}")

try:  # reuse the KB normalizer so uz/ru/cyrillic queries match tree keywords
    from kb.src.normalize import normalize as _kb_normalize
except Exception:  # pragma: no cover
    _kb_normalize = None


def _normalize(text: str) -> str:
    if _kb_normalize is not None:
        return str(_kb_normalize(text))
    return text.lower()


class DiagnosticError(ValueError):
    """A tree/card reference is inconsistent."""


class DiagnosticEngine:
    """Serve and advance the diagnostic decision trees."""

    def __init__(self, bundle: DiagnosticBundle) -> None:
        self._trees = {tree.id: tree for tree in bundle.trees}
        self._cards = {card.id: card for card in bundle.cards}
        self._nodes = {
            (tree.id, node.id): node for tree in bundle.trees for node in tree.nodes
        }
        self._validate()

    @classmethod
    def from_json(cls, path: Path) -> DiagnosticEngine:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(DiagnosticBundle.model_validate(raw))

    def _validate(self) -> None:
        for tree in self._trees.values():
            if (tree.id, tree.root) not in self._nodes:
                raise DiagnosticError(f"{tree.id}: root node '{tree.root}' is missing")
            for node in tree.nodes:
                for option in node.options:
                    if option.next_node is None and option.card is None:
                        raise DiagnosticError(
                            f"{tree.id}/{node.id}/{option.value}: dead-end option"
                        )
                    if option.next_node and (tree.id, option.next_node) not in self._nodes:
                        raise DiagnosticError(
                            f"{tree.id}/{node.id}: unknown next_node '{option.next_node}'"
                        )
                    if option.card and option.card not in self._cards:
                        raise DiagnosticError(
                            f"{tree.id}/{node.id}: unknown card '{option.card}'"
                        )

    def trees(self) -> list[DecisionTree]:
        return list(self._trees.values())

    def get_tree(self, tree_id: str) -> DecisionTree | None:
        return self._trees.get(tree_id)

    def get_node(self, tree_id: str, node_id: str) -> DiagnosticNode | None:
        return self._nodes.get((tree_id, node_id))

    def get_card(self, card_id: str) -> ResolutionCard | None:
        return self._cards.get(card_id)

    def match_tree(self, query: str) -> DecisionTree | None:
        """Pick the tree whose keywords best overlap the free-text problem."""
        terms = set(_TOKEN.findall(_normalize(query)))
        if not terms:
            return None
        best: DecisionTree | None = None
        best_score = 0
        for tree in self._trees.values():
            score = sum(1 for keyword in tree.keywords if _normalize(keyword) in terms)
            if score > best_score:
                best, best_score = tree, score
        return best if best_score > 0 else None

    def answer(
        self, tree_id: str, node_id: str, value: str
    ) -> tuple[DiagnosticNode | None, ResolutionCard | None]:
        """Advance from one node given the chosen option value.

        Returns (next_node, None), (None, card) or (None, None) when the value is
        not a valid option for that node.
        """
        node = self.get_node(tree_id, node_id)
        if node is None:
            return None, None
        for option in node.options:
            if option.value == value:
                next_node = (
                    self.get_node(tree_id, option.next_node) if option.next_node else None
                )
                card = self.get_card(option.card) if option.card else None
                return next_node, card
        return None, None
