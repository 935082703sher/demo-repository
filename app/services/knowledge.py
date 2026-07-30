"""Local approved/demo-only knowledge loading and deterministic retrieval."""

from __future__ import annotations

import hashlib
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
            if not record_is_eligible(record, current_time):
                continue
            score = sum(normalize_text(keyword) in terms for keyword in record.keywords)
            if score >= 2:
                ranked.append((score, record))

        ranked.sort(key=lambda item: (-item[0], item[1].document_id))
        return [record for _, record in ranked[:3]]

    def validation_results(
        self,
        *,
        now: datetime | None = None,
    ) -> tuple[list[str], list[str]]:
        """Return eligible and rejected IDs for import validation."""
        current_time = now or datetime.now(UTC)
        eligible: list[str] = []
        rejected: list[str] = []
        for record in self._records:
            target = eligible if record_is_eligible(record, current_time) else rejected
            target.append(record.document_id)
        return eligible, rejected


def content_hash(content: str) -> str:
    """Return the canonical SHA-256 hex digest used by approved records."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def record_is_eligible(record: KnowledgeRecord, now: datetime) -> bool:
    """Enforce approval and synthetic-fixture boundaries before retrieval."""
    if not record.active or record.status is KnowledgeStatus.INACTIVE:
        return False
    if record.expires_at is not None and record.expires_at <= now:
        return False
    if record.valid_until is not None and record.valid_until <= now:
        return False
    if record.valid_from is not None and record.valid_from > now:
        return False

    if record.status is KnowledgeStatus.DEMO_ONLY:
        warning = record.content.casefold()
        return (
            record.synthetic
            and not record.approved
            and ("demo fixture" in warning or "demo manba" in warning or "демо-источник" in warning)
        )

    return (
        record.approved
        and not record.synthetic
        and record.approved_at is not None
        and record.approved_by is not None
        and bool(record.approved_by.strip())
        and record.valid_from is not None
        and record.source_url is not None
        and record.source_url.startswith("https://")
        and record.content_hash is not None
        and record.content_hash == content_hash(record.content)
    )
