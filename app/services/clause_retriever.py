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
from app.services.embeddings import cosine as _cosine
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

    def __init__(
        self, bundle: ClauseBundle, clause_vectors: dict[str, list[float]] | None = None
    ) -> None:
        self._bundle = bundle
        self._by_clause = bundle.by_clause()
        # Pre-normalise each clause's keywords and subject tokens once.
        # Score on the curated Uzbek/Russian keywords only. The subject is an English
        # identifier for the code, not a retrieval signal, and matching its tokens as
        # substrings causes false hits (e.g. "and" inside "qanday"), so it is excluded.
        self._terms: dict[str, list[tuple[str, str]]] = {
            rule.clause: [(_normalize(k), k) for k in rule.keywords] for rule in bundle.rules
        }
        # Optional semantic vectors, keyed by clause; empty means lexical-only.
        self._vectors: dict[str, list[float]] = clause_vectors or {}

    @classmethod
    def from_json(cls, path: object, vectors_path: object | None = None) -> ClauseRetriever:
        import json
        from pathlib import Path

        vectors: dict[str, list[float]] = {}
        if vectors_path is not None and Path(str(vectors_path)).exists():
            vectors = json.loads(Path(str(vectors_path)).read_text(encoding="utf-8"))
        return cls(ClauseBundle.from_json(Path(str(path))), vectors)

    @property
    def has_vectors(self) -> bool:
        return bool(self._vectors)

    @property
    def clauses(self) -> list[Clause]:
        return list(self._bundle.rules)

    def retrieve(
        self,
        message: str,
        *,
        top_k: int = 8,
        expand: bool = True,
        query_vector: list[float] | None = None,
    ) -> list[ClauseHit]:
        """Return the clauses relevant to the message, most relevant first.

        Scoring is lexical over normalised keywords (a longer keyword phrase that
        matches counts for more than a single token). When a ``query_vector`` and
        precomputed clause vectors are available, semantic similarity is blended in
        and strongly-similar clauses are recalled EVEN WITH NO shared word - so a
        paraphrase finds the right clause by meaning. The top hits' related clauses
        are then added at a lower score (the rule graph). An off-topic message still
        retrieves nothing: a clause needs either a lexical hit or real semantic
        similarity, not a default.
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

        # Semantic layer: blend cosine similarity into lexical hits, and recall a
        # clause on its own when it is clearly on-topic by meaning (>= floor), even
        # with zero shared words. This is what lets paraphrases and typos find the
        # right clause without hand-written synonyms. Semantic-only recalls are capped
        # to the few strongest so a small embedding model's fuzzy matches add recall
        # without flooding the evidence with noise.
        if query_vector and self._vectors:
            floor = 0.40
            semantic_only: list[tuple[float, Clause]] = []
            for rule in self._bundle.rules:
                vec = self._vectors.get(rule.clause)
                if not vec:
                    continue
                sim = _cosine(query_vector, vec)
                if rule.clause in scored:
                    scored[rule.clause] = ClauseHit(
                        rule,
                        scored[rule.clause].score + 2.0 * sim,
                        scored[rule.clause].matched_terms,
                    )
                elif sim >= floor:
                    semantic_only.append((sim, rule))
            for sim, rule in sorted(semantic_only, key=lambda t: t[0], reverse=True)[:5]:
                scored[rule.clause] = ClauseHit(rule, 1.5 * sim, [f"~{sim:.2f}"])

        if expand:
            for hit in list(scored.values()):
                for related in hit.clause.related_rules:
                    if related not in scored and related in self._by_clause:
                        scored[related] = ClauseHit(
                            self._by_clause[related], hit.score * 0.3, [], via_graph=True
                        )

        ranked = sorted(scored.values(), key=lambda h: h.score, reverse=True)
        return ranked[:top_k]
