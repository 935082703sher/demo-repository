"""Dynamic retrieval over the full VMQ-778 clause set - not phrase matching.

The retriever finds the clauses relevant to a free-form situation however it is
phrased: it normalises the text (Cyrillic transliterated to Latin, apostrophes
dropped - the same `_normalize` the rest of the system uses, so Uzbek Latin, Uzbek
Cyrillic, Russian and mixed input all collapse to one form), scores each clause by
how many of its keywords and subject tokens the situation mentions, and then expands
the top hits along the rule graph (``related_rules``) so a specific clause pulls in
the general one it rests on. A single generic hit never ends the search.

It returns ranked clauses with the terms that matched, so the reasoning layer can
show why each clause was selected. It selects; it does not write the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.legal_clauses import Clause, ClauseBundle
from app.services.fact_extraction import _normalize


@dataclass(frozen=True)
class ClauseHit:
    """One retrieved clause with its score and the terms that matched it."""

    clause: Clause
    score: float
    matched_terms: list[str] = field(default_factory=list)
    via_graph: bool = False


def _norm_tokens(text: str) -> set[str]:
    return {t for t in _normalize(text).split() if len(t) > 2}


class ClauseRetriever:
    """Rank the clauses relevant to a situation, with rule-graph expansion."""

    def __init__(self, bundle: ClauseBundle) -> None:
        self._bundle = bundle
        self._by_clause = bundle.by_clause()
        # Pre-normalise each clause's keywords and subject tokens once.
        # Score on the curated Uzbek/Russian keywords only. The subject is an English
        # identifier for the code, not a retrieval signal, and matching its tokens as
        # substrings causes false hits (e.g. "and" inside "qanday"), so it is excluded.
        self._terms: dict[str, list[tuple[str, str]]] = {
            rule.clause: [(_normalize(k), k) for k in rule.keywords] for rule in bundle.rules
        }

    @classmethod
    def from_json(cls, path: object) -> ClauseRetriever:
        from pathlib import Path

        return cls(ClauseBundle.from_json(Path(str(path))))

    @property
    def clauses(self) -> list[Clause]:
        return list(self._bundle.rules)

    def retrieve(self, message: str, *, top_k: int = 8, expand: bool = True) -> list[ClauseHit]:
        """Return the clauses relevant to the message, most relevant first.

        Scoring is lexical over normalised keywords (a longer keyword phrase that
        matches counts for more than a single token), then the top hits' related
        clauses are added at a lower score so the specific and the general travel
        together. Clauses with no match are left out, so an off-topic message
        retrieves nothing rather than a default clause.
        """
        norm = _normalize(message)
        tokens = _norm_tokens(message)
        scored: dict[str, ClauseHit] = {}
        for rule in self._bundle.rules:
            matched: list[str] = []
            score = 0.0
            for norm_term, original in self._terms[rule.clause]:
                if not norm_term:
                    continue
                if " " in norm_term:
                    if norm_term in norm:
                        score += 2.5
                        matched.append(original)
                elif norm_term in tokens or norm_term in norm:
                    score += 1.0
                    matched.append(original)
            if score > 0:
                scored[rule.clause] = ClauseHit(rule, score, matched)

        if expand:
            for hit in list(scored.values()):
                for related in hit.clause.related_rules:
                    if related not in scored and related in self._by_clause:
                        scored[related] = ClauseHit(
                            self._by_clause[related], hit.score * 0.3, [], via_graph=True
                        )

        ranked = sorted(scored.values(), key=lambda h: h.score, reverse=True)
        return ranked[:top_k]
