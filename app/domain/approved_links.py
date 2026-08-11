"""Server-owned official-link registry contracts for Stage 3B."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from app.domain.governance import ApprovalStatus
from app.domain.schemas import StrictModel


class LinkLanguage(StrEnum):
    """Language applicability, including explicitly multilingual pages."""

    UZ = "uz"
    RU = "ru"
    EN = "en"
    MULTILINGUAL = "multilingual"


class ApprovedLinkEntry(StrictModel):
    """Reviewed metadata that remains unavailable until separate owner activation."""

    link_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    url: AnyHttpUrl
    language: LinkLanguage
    purpose: str = Field(min_length=3, max_length=200)
    owner: str = Field(min_length=3, max_length=200)
    approval_status: ApprovalStatus = ApprovalStatus.PENDING_REVIEW
    verified_at: datetime
    review_due_at: datetime
    active: bool = False
    runtime_eligible: bool = False
    test_only: bool = True

    @field_validator("verified_at", "review_due_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("link timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_future_review(self) -> ApprovedLinkEntry:
        if self.review_due_at <= self.verified_at:
            raise ValueError("link review date must follow verification")
        if (
            self.active or self.runtime_eligible
        ) and self.approval_status is not ApprovalStatus.APPROVED:
            raise ValueError("active runtime links require explicit approval")
        if self.active != self.runtime_eligible:
            raise ValueError("active and runtime eligibility must change together")
        return self
