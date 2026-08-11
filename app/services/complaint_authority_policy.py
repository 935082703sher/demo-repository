"""Deterministic anti-invention checks for Stage 3A complaint handling."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.complaint_workflow import HandoffReason, MessageKey, ProtectedClaim

_OFFICIAL_INTEGRATION_ONLY = frozenset(
    {
        ProtectedClaim.RESPONSIBLE_DEPARTMENT_ASSIGNMENT,
        ProtectedClaim.COMPLAINT_ACCEPTANCE,
        ProtectedClaim.CASE_NUMBER,
        ProtectedClaim.COMPLAINT_STATUS,
        ProtectedClaim.FINAL_DECISION,
        ProtectedClaim.ENFORCEMENT_ACTION,
    }
)


@dataclass(frozen=True, slots=True)
class AuthorityContext:
    """Server-owned evidence state; model output cannot modify it."""

    approved_active_source_ids: tuple[str, ...] = ()
    official_integration_verified: bool = False


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    """Typed allow/block result without citizen-facing factual content."""

    allowed: bool
    handoff_reason: HandoffReason | None
    message_key: MessageKey | None


def evaluate_protected_claim(
    claim: ProtectedClaim,
    *,
    context: AuthorityContext,
) -> AuthorityDecision:
    """Require trusted server context for protected legal or official claims."""
    if claim in _OFFICIAL_INTEGRATION_ONLY:
        allowed = context.official_integration_verified
    else:
        allowed = bool(context.approved_active_source_ids)
    if allowed:
        return AuthorityDecision(allowed=True, handoff_reason=None, message_key=None)
    return AuthorityDecision(
        allowed=False,
        handoff_reason=HandoffReason.APPROVED_INFORMATION_UNAVAILABLE,
        message_key=MessageKey.UNSUPPORTED_AUTHORITY_REQUEST,
    )
