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

    def validate(
        self,
        result: LLMResult,
        retrieved_records: list[KnowledgeRecord],
    ) -> GroundingDecision:
        """Require non-empty, unique, server-owned citations."""
        if not result.text.strip() or not result.citations:
            return GroundingDecision(False)
        records_by_id = {record.document_id: record for record in retrieved_records}
        if len(records_by_id) != len(retrieved_records):
            return GroundingDecision(False)
        if any(source_id not in records_by_id for source_id in result.citations):
            return GroundingDecision(False)

        cited: list[KnowledgeRecord] = []
        seen: set[str] = set()
        for source_id in result.citations:
            if source_id not in seen:
                cited.append(records_by_id[source_id])
                seen.add(source_id)
        return GroundingDecision(True, tuple(cited))
