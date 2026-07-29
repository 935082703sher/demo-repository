"""Local approved/demo-only knowledge loading and deterministic retrieval."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from app.domain.enums import Category, KnowledgeStatus, Language
from app.domain.schemas import KnowledgeRecord
from app.services.classifier import normalize_text


class KnowledgeService:
    """Search active versioned records without accepting citizen text as knowledge."""

    def __init__(self, records: list[KnowledgeRecord]) -> None:
        self._records = tuple(records)

    @classmethod
    def from_json(cls, path: Path) -> KnowledgeService:
        """Load and validate the local fixture at application startup."""
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = TypeAdapter(list[KnowledgeRecord]).validate_python(raw)
        return cls(records)

    def search(
        self,
        query: str,
        language: Language,
        category: Category,
        *,
        now: datetime | None = None,
    ) -> list[KnowledgeRecord]:
        """Return only records whose evidence is active and relevant.

        Requiring two keyword matches prevents a category word alone from being
        mistaken for evidence supporting a fee, deadline, status, or procedure.
        """
        current_time = now or datetime.now(UTC)
        terms = set(normalize_text(query).split())
        ranked: list[tuple[int, KnowledgeRecord]] = []

        for record in self._records:
            if record.language != language or record.category != category:
                continue
            if record.status not in {KnowledgeStatus.APPROVED, KnowledgeStatus.DEMO_ONLY}:
                continue
            if record.expires_at is not None and record.expires_at <= current_time:
                continue
            if record.status is KnowledgeStatus.APPROVED and record.approved_at is None:
                continue
            score = sum(normalize_text(keyword) in terms for keyword in record.keywords)
            if score >= 2:
                ranked.append((score, record))

        ranked.sort(key=lambda item: (-item[0], item[1].document_id))
        return [record for _, record in ranked[:3]]
