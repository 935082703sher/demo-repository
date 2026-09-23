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

# Domain words that name a topic area, not a specific problem. They are a real
# signal (a bare 'imei' message should still reach the primary IMEI tree), but a
# specific word like 'bloklandi' must outrank them, so they weigh less.
_GENERIC_TOKENS = frozenset({"imei", "mnp"})
_GENERIC_WEIGHT = 0.5

try:  # reuse the KB normalizer so uz/ru/cyrillic queries match tree keywords
    from kb.src.normalize import normalize as _kb_normalize
except Exception:  # pragma: no cover
    _kb_normalize = None


def _normalize(text: str) -> str:
    if _kb_normalize is not None:
        return str(_kb_normalize(text))
    return text.lower()


def _stem_match(token: str, terms: set[str]) -> bool:
    """True if a keyword token overlaps a query term by stem (substring either way).

    Uzbek/Russian are agglutinative, so exact token equality misses inflections
    ('operator' vs 'operatorga', 'blok' vs 'bloklandi'). Substring matching keeps
    the rule transparent while tolerating common suffixes.
    """
    return any(token in term or term in token for term in terms)


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

    def _tree_score(self, tree: DecisionTree, terms: set[str]) -> float:
        """Score one tree against the query terms; multi-word keywords are phrases.

        A single-token keyword matches when its token overlaps a query term by
        stem. A multi-token keyword is a phrase: it matches only when every one of
        its tokens overlaps some query term, so 'регистрация imei' needs the
        registration word too, not merely 'imei'. Each distinct query term counts
        once at the weight of the strongest keyword that matched it (a generic
        domain word weighs less), so a repeated or generic word cannot inflate a
        score above a specific match.
        """
        weights: dict[str, float] = {}
        for keyword in tree.keywords:
            tokens = _TOKEN.findall(_normalize(keyword))
            if not tokens:
                continue
            hits: list[tuple[str, float]] = []
            generic = len(tokens) == 1 and tokens[0] in _GENERIC_TOKENS
            weight = _GENERIC_WEIGHT if generic else 1.0
            for token in tokens:
                hit = next((term for term in terms if token in term or term in token), None)
                if hit is None:
                    hits = []
                    break
                hits.append((hit, weight))
            for term, term_weight in hits:
                weights[term] = max(weights.get(term, 0.0), term_weight)
        return sum(weights.values())

    def _keyword_scores(self, query: str) -> dict[str, float]:
        """Score every tree by its weighted overlap with the query terms."""
        terms = set(_TOKEN.findall(_normalize(query)))
        if not terms:
            return {}
        return {tree.id: self._tree_score(tree, terms) for tree in self._trees.values()}

    def match_tree(self, query: str) -> DecisionTree | None:
        """Pick the tree whose keywords best overlap the free-text problem."""
        scores = self._keyword_scores(query)
        if not scores:
            return None
        best_id = max(scores, key=lambda tid: scores[tid])
        return self._trees[best_id] if scores[best_id] > 0 else None

    def walk(
        self, tree_id: str, facts: dict[str, str], *, max_steps: int = 20
    ) -> tuple[str, DiagnosticNode | ResolutionCard | None]:
        """Walk from the tree root using known facts (see advance)."""
        tree = self.get_tree(tree_id)
        if tree is None:
            return ("stuck", None)
        return self.advance(tree_id, tree.root, facts, max_steps=max_steps)

    def advance(
        self, tree_id: str, node_id: str, facts: dict[str, str], *, max_steps: int = 20
    ) -> tuple[str, DiagnosticNode | ResolutionCard | None]:
        """Advance from a node, auto-skipping questions whose fact is already known.

        Returns ("ask", node) for the next question the case still needs,
        ("resolve", card) when a fact completes a path, or ("stuck", None). A node
        whose fact is known is auto-advanced, so the user is never asked what they
        already told; a node without a fact (or an unknown one) is asked.
        """
        node = self.get_node(tree_id, node_id)
        for _ in range(max_steps):
            if node is None:
                return ("stuck", None)
            if node.fact and node.fact in facts:
                value = facts[node.fact]
                option = next((o for o in node.options if o.fact_value == value), None)
                if option is not None:
                    if option.card is not None:
                        return ("resolve", self.get_card(option.card))
                    node = self.get_node(tree_id, option.next_node) if option.next_node else None
                    continue
            return ("ask", node)
        return ("stuck", None)

    def map_answer(self, tree_id: str, node_id: str, message: str) -> str | None:
        """Map a free-text reply to one of the node's option values.

        Deterministic keyword overlap against every option's labels (uz/ru/en)
        and its value; returns the best match or None when nothing overlaps.
        """
        node = self.get_node(tree_id, node_id)
        if node is None:
            return None
        text = _normalize(message).strip()
        terms = set(_TOKEN.findall(text))
        for option in node.options:
            if option.value == text:
                return option.value
        best: str | None = None
        best_score = 0
        for option in node.options:
            option_terms: set[str] = set()
            for label in (option.label.uz, option.label.ru, option.label.en or "", option.value):
                option_terms |= set(_TOKEN.findall(_normalize(label)))
            score = sum(1 for term in terms if _stem_match(term, option_terms))
            if score > best_score:
                best, best_score = option.value, score
        return best if best_score > 0 else None

    def trees_for_domain(self, domain: str) -> list[DecisionTree]:
        return [tree for tree in self._trees.values() if tree.domain == domain]

    def route(self, query: str) -> tuple[DecisionTree | None, str | None]:
        """Route free text to a tree, or to a domain when the tree is ambiguous.

        Returns (tree, None) for one clear winner, (None, domain) when several
        trees of the same domain tie (ask which topic), or (None, None) for no
        match at all (offer the full menu).
        """
        scores = self._keyword_scores(query)
        if not scores:
            return None, None
        best = max(scores.values())
        if best <= 0:
            return None, None
        top = [self._trees[tid] for tid, score in scores.items() if score == best]
        if len(top) == 1:
            return top[0], None
        domains = {tree.domain for tree in top}
        if len(domains) == 1:
            return None, next(iter(domains))
        return top[0], None

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
