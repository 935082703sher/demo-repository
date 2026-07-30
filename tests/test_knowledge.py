"""Knowledge activation and expiry tests."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import Category, KnowledgeStatus, Language
from app.domain.schemas import KnowledgeRecord
from app.services.knowledge import KnowledgeService


@pytest.mark.parametrize(
    ("status", "expires_offset", "expected_count"),
    [
        (KnowledgeStatus.DEMO_ONLY, 1, 1),
        (KnowledgeStatus.DEMO_ONLY, -1, 0),
        (KnowledgeStatus.INACTIVE, 1, 0),
    ],
)
def test_expired_and_inactive_records_are_rejected(
    status: KnowledgeStatus,
    expires_offset: int,
    expected_count: int,
) -> None:
    now = datetime.now(UTC)
    record = KnowledgeRecord(
        document_id="TEST-001",
        title="Synthetic test record",
        language=Language.EN,
        category=Category.IMEI,
        content="DEMO FIXTURE — Synthetic only.",
        keywords=["demo", "fixture", "imei"],
        source_url=None,
        version="test",
        status=status,
        approved=False,
        active=True,
        synthetic=True,
        approved_by=None,
        approved_at=None,
        valid_from=None,
        valid_until=None,
        expires_at=now + timedelta(days=expires_offset),
        content_hash=None,
    )
    service = KnowledgeService([record])

    results = service.search("IMEI demo fixture", Language.EN, Category.IMEI, now=now)

    assert len(results) == expected_count


def test_approved_record_without_approval_date_is_rejected() -> None:
    record = KnowledgeRecord(
        document_id="TEST-002",
        title="Unapproved test record",
        language=Language.EN,
        category=Category.IMEI,
        content="Synthetic only.",
        keywords=["demo", "fixture"],
        source_url=None,
        version="test",
        status=KnowledgeStatus.APPROVED,
        approved=False,
        active=True,
        synthetic=False,
        approved_by=None,
        approved_at=None,
        valid_from=None,
        valid_until=None,
        expires_at=None,
        content_hash=None,
    )

    assert (
        KnowledgeService([record]).search(
            "IMEI demo fixture",
            Language.EN,
            Category.IMEI,
        )
        == []
    )
