"""Local retrieval of anonymized case examples used only for response guidance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.domain.enums import Category
from app.services.classifier import normalize_text


@dataclass(frozen=True, slots=True)
class CaseGuidance:
    """A non-authoritative, anonymized writing and triage example."""

    document_id: str
    text: str


class CaseGuidanceService:
    """Search local masked response-letter examples without treating them as facts."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = tuple(
            row
            for row in rows
            if row.get("source_type") == "javob_xati"
            and row.get("pii_masked") is True
            and row.get("has_substance") is True
        )

    @classmethod
    def from_jsonl(cls, path: Path) -> CaseGuidanceService:
        if not path.exists():
            return cls([])
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        return cls(rows)

    def search(self, query: str, category: Category, *, limit: int = 2) -> list[CaseGuidance]:
        terms = set(normalize_text(query).split())
        scored: list[tuple[int, dict[str, object]]] = []
        for row in self._rows:
            if row.get("domain") != category.value:
                continue
            haystack = normalize_text(str(row.get("text_norm") or row.get("text") or ""))
            score = sum(term in haystack for term in terms if len(term) >= 3)
            if score:
                scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], str(item[1].get("id"))))
        return [
            CaseGuidance(document_id=str(row["id"]), text=str(row["text"])[:1200])
            for _, row in scored[:limit]
        ]
