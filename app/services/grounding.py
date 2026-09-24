"""Deterministic authorization of provider citations against retrieved records."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.schemas import KnowledgeRecord, LLMResult


@dataclass(frozen=True, slots=True)
class GroundingDecision:
    """Trusted cited records or a rejected provider answer."""

    allowed: bool
    cited_records: tuple[KnowledgeRecord, ...] = ()


class GroundingValidator:
    """Reject source IDs the provider was not supplied."""

    def authorize(self, text: str, citations: list[str], allowed_ids: list[str]) -> bool:
        """True when a non-empty answer cites only supplied source IDs.

        Set-based (duplicates tolerated) so it also fits chunk retrieval, where
        several passages share one document id.
        """
        if not text.strip() or not citations:
            return False
        allowed = set(allowed_ids)
        return all(source_id in allowed for source_id in citations)

    def validate(
        self,
        result: LLMResult,
        retrieved_records: list[KnowledgeRecord],
    ) -> GroundingDecision:
        """Require non-empty, unique, server-owned citations."""
        records_by_id = {record.document_id: record for record in retrieved_records}
        if len(records_by_id) != len(retrieved_records):
            return GroundingDecision(False)
        if not self.authorize(result.text, result.citations, list(records_by_id)):
            return GroundingDecision(False)

        cited: list[KnowledgeRecord] = []
        seen: set[str] = set()
        for source_id in result.citations:
            if source_id not in seen:
                cited.append(records_by_id[source_id])
                seen.add(source_id)
        return GroundingDecision(True, tuple(cited))
