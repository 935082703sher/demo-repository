"""Approved knowledge metadata, import, and retrieval boundaries."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.enums import Category, KnowledgeStatus, Language
from app.domain.schemas import KnowledgeRecord
from app.services.knowledge import KnowledgeService, content_hash
from app.services.knowledge_import import validate_knowledge_file


def approved_record(now: datetime) -> KnowledgeRecord:
    """Build a fully approved synthetic test record with no official facts."""
    content = "Synthetic approved test content for validation only."
    return KnowledgeRecord(
        document_id="TEST-APPROVED-001",
        title="Synthetic approved test source",
        language=Language.EN,
        category=Category.IMEI,
        content=content,
        keywords=["synthetic", "approved"],
        source_url="https://example.invalid/approved-source",
        version="1",
        status=KnowledgeStatus.APPROVED,
        approved=True,
        active=True,
        synthetic=False,
        approved_by="test-authorized-role",
        approved_at=now - timedelta(days=1),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
        expires_at=None,
        content_hash=content_hash(content),
    )


@pytest.mark.parametrize(
    "update",
    [
        {"approved": False},
        {"active": False},
        {"status": KnowledgeStatus.INACTIVE},
        {"approved_by": None},
        {"approved_at": None},
        {"valid_from": None},
        {"source_url": None},
        {"source_url": "http://example.invalid/not-secure"},
        {"content_hash": None},
        {"content_hash": "0" * 64},
        {"synthetic": True},
    ],
)
def test_invalid_approved_metadata_is_excluded(update: dict[str, object]) -> None:
    now = datetime(2026, 7, 30, tzinfo=UTC)
    record = approved_record(now).model_copy(update=update)

    assert (
        KnowledgeService([record]).search(
            "synthetic approved IMEI",
            Language.EN,
            Category.IMEI,
            now=now,
        )
        == []
    )


def test_expired_not_yet_valid_and_wrong_language_records_are_excluded() -> None:
    now = datetime(2026, 7, 30, tzinfo=UTC)
    base = approved_record(now)
    expired = base.model_copy(update={"valid_until": now})
    future = base.model_copy(update={"valid_from": now + timedelta(seconds=1)})
    service = KnowledgeService([expired, future, base])

    assert service.search("synthetic approved IMEI", Language.RU, Category.IMEI, now=now) == []
    assert service.search("synthetic approved IMEI", Language.EN, Category.IMEI, now=now) == [base]


def test_synthetic_fixture_cannot_be_mistaken_for_approved() -> None:
    now = datetime(2026, 7, 30, tzinfo=UTC)
    record = approved_record(now).model_copy(
        update={
            "status": KnowledgeStatus.DEMO_ONLY,
            "approved": False,
            "synthetic": True,
            "content": "Synthetic content without the mandatory demo warning.",
            "source_url": None,
            "approved_by": None,
            "approved_at": None,
            "content_hash": None,
        }
    )

    assert KnowledgeService([record]).validation_results(now=now)[0] == []


def test_import_rejects_malformed_record(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps([{"document_id": "missing-required-fields"}]))

    with pytest.raises(ValidationError):
        validate_knowledge_file(candidate)


def test_import_reports_ineligible_records_without_content(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    record = approved_record(now).model_copy(update={"approved": False})
    candidate = tmp_path / "candidate.json"
    candidate.write_text(record.model_dump_json())
    candidate.write_text(f"[{candidate.read_text()}]")

    report = validate_knowledge_file(candidate)

    assert report.total == 1
    assert report.eligible_ids == []
    assert report.rejected_ids == ["TEST-APPROVED-001"]
