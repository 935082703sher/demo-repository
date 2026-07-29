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
        content="Synthetic only.",
        keywords=["demo", "fixture", "imei"],
        source_url=None,
        version="test",
        status=status,
        approved_at=None,
        expires_at=now + timedelta(days=expires_offset),
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
        approved_at=None,
        expires_at=None,
    )

    assert (
        KnowledgeService([record]).search(
            "IMEI demo fixture",
            Language.EN,
            Category.IMEI,
        )
        == []
    )
