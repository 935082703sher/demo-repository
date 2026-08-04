"""Fail-closed activation and transition policy for Demo 3 knowledge."""

from __future__ import annotations

import hmac
from datetime import datetime

from app.domain.enums import Language
from app.domain.governance import (
    ActivationStatus,
    ApprovalStatus,
    GovernedKnowledgeRecord,
    KnowledgeSource,
    governed_content_hash,
)

_APPROVAL_TRANSITIONS: dict[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.DRAFT: frozenset({ApprovalStatus.PENDING_REVIEW}),
    ApprovalStatus.PENDING_REVIEW: frozenset(
        {ApprovalStatus.DRAFT, ApprovalStatus.APPROVED, ApprovalStatus.WITHDRAWN}
    ),
    ApprovalStatus.APPROVED: frozenset({ApprovalStatus.WITHDRAWN}),
    ApprovalStatus.WITHDRAWN: frozenset(),
}

_ACTIVATION_TRANSITIONS: dict[ActivationStatus, frozenset[ActivationStatus]] = {
    ActivationStatus.INACTIVE: frozenset({ActivationStatus.ACTIVE, ActivationStatus.WITHDRAWN}),
    ActivationStatus.ACTIVE: frozenset(
        {
            ActivationStatus.INACTIVE,
            ActivationStatus.EXPIRED,
            ActivationStatus.SUPERSEDED,
            ActivationStatus.WITHDRAWN,
        }
    ),
    ActivationStatus.EXPIRED: frozenset({ActivationStatus.INACTIVE, ActivationStatus.WITHDRAWN}),
    ActivationStatus.SUPERSEDED: frozenset({ActivationStatus.WITHDRAWN}),
    ActivationStatus.WITHDRAWN: frozenset(),
}


def approval_transition_allowed(current: ApprovalStatus, target: ApprovalStatus) -> bool:
    """Return whether the explicit human-review transition is permitted."""
    return target in _APPROVAL_TRANSITIONS[current]


def activation_transition_allowed(current: ActivationStatus, target: ActivationStatus) -> bool:
    """Return whether the runtime lifecycle transition is permitted."""
    return target in _ACTIVATION_TRANSITIONS[current]


def source_activation_failures(source: KnowledgeSource, *, now: datetime) -> tuple[str, ...]:
    """List safe policy codes that prevent source activation."""
    failures: list[str] = []
    if source.approval_status is not ApprovalStatus.APPROVED:
        failures.append("source_not_approved")
    if source.activation_status is not ActivationStatus.ACTIVE:
        failures.append("source_not_active")
    if source.quarantined:
        failures.append("source_quarantined")
    if source.conflict_ids:
        failures.append("source_conflict")
    if not _present(source.content_owner_department):
        failures.append("source_owner_missing")
    if not _present(source.approved_by) or source.approved_at is None:
        failures.append("source_approval_evidence_missing")
    if source.source_checked_at is None:
        failures.append("source_check_missing")
    elif source.source_checked_at > now:
        failures.append("source_check_in_future")
    if source.review_due_at is None:
        failures.append("source_review_due_missing")
    elif source.review_due_at <= now:
        failures.append("source_review_overdue")
    if source.observed_sha256 is None or not hmac.compare_digest(
        source.expected_sha256, source.observed_sha256
    ):
        failures.append("source_hash_mismatch")
    return tuple(failures)


def record_activation_failures(
    record: GovernedKnowledgeRecord,
    source: KnowledgeSource,
    *,
    language: Language,
    now: datetime,
) -> tuple[str, ...]:
    """List every reason a record is forbidden from citizen retrieval."""
    failures = list(source_activation_failures(source, now=now))
    if record.source_id != source.source_id:
        failures.append("source_id_mismatch")
    if record.approval_status is not ApprovalStatus.APPROVED:
        failures.append("record_not_approved")
    if record.activation_status is not ActivationStatus.ACTIVE:
        failures.append("record_not_active")
    if record.quarantined:
        failures.append("record_quarantined")
    if record.conflict_ids:
        failures.append("record_conflict")
    if record.language is not language:
        failures.append("wrong_language")
    if not _present(record.content_owner_department):
        failures.append("record_owner_missing")
    if not _present(record.approved_by) or record.approved_at is None:
        failures.append("record_approval_evidence_missing")
    if record.valid_from is None:
        failures.append("valid_from_missing")
    elif record.valid_from > now:
        failures.append("not_yet_valid")
    if record.valid_until is not None and record.valid_until <= now:
        failures.append("record_expired")
    if record.source_checked_at is None:
        failures.append("record_source_check_missing")
    elif record.source_checked_at > now:
        failures.append("record_source_check_in_future")
    if record.review_due_at is None:
        failures.append("record_review_due_missing")
    elif record.review_due_at <= now:
        failures.append("record_review_overdue")
    if record.time_sensitive and record.valid_until is None:
        failures.append("time_sensitive_valid_until_missing")
    calculated_hash = governed_content_hash(question=record.question, answer=record.answer)
    if not hmac.compare_digest(record.content_sha256, calculated_hash):
        failures.append("record_hash_mismatch")
    return tuple(dict.fromkeys(failures))


def record_is_retrievable(
    record: GovernedKnowledgeRecord,
    source: KnowledgeSource,
    *,
    language: Language,
    now: datetime,
) -> bool:
    """Require a current, approved, active, conflict-free source and record."""
    return not record_activation_failures(record, source, language=language, now=now)


def _present(value: str | None) -> bool:
    return value is not None and bool(value.strip())
