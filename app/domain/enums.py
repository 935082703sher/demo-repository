"""Closed sets used by the API and deterministic workflow."""

from enum import StrEnum


class Language(StrEnum):
    """Languages supported by Demo 1."""

    UZ = "uz"
    RU = "ru"
    EN = "en"


class Category(StrEnum):
    """Approved primary request categories."""

    IMEI = "imei"
    MNP = "mnp"
    NUMBER_CODES = "number_codes"
    NETWORK_QUALITY = "network_quality"
    WEBSITE_ISSUE = "website_issue"
    OTHER = "other"


class ConversationState(StrEnum):
    """Backend-enforced conversation states used in Demo 1."""

    LANGUAGE_SELECTION = "language_selection"
    CATEGORY_IDENTIFICATION = "category_identification"
    ANSWER = "answer"
    FOLLOW_UP = "follow_up"
    DRAFT_REVIEW = "draft_review"
    DRAFT_EDIT = "draft_edit"
    AWAITING_CONSENT = "awaiting_consent"
    SUBMISSION_FAILED = "submission_failed"
    HUMAN_HANDOFF = "human_handoff"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class ResponseType(StrEnum):
    """Semantic response type for website rendering."""

    LANGUAGE_SELECTION = "language_selection"
    ANSWER = "answer"
    FOLLOW_UP = "follow_up"
    REFUSAL = "refusal"
    HUMAN_HANDOFF = "human_handoff"
    DRAFT = "draft"
    SUBMISSION_RESULT = "submission_result"


class EscalationReason(StrEnum):
    """Reasons for stopping ordinary automated handling."""

    CITIZEN_REQUEST = "citizen_requested_human"
    EMERGENCY = "emergency_or_immediate_danger"
    THREAT_OR_VIOLENCE = "threat_or_violence"
    SELF_HARM = "self_harm"
    SENSITIVE_DATA = "sensitive_data"
    CYBERSECURITY = "serious_cybersecurity_incident"
    LEGAL_INTERPRETATION = "legal_interpretation"
    OFFICIAL_DECISION_DISPUTE = "official_decision_dispute"
    MISCONDUCT_ALLEGATION = "misconduct_allegation"
    NO_APPROVED_SOURCE = "no_approved_source"
    UNCLEAR_AFTER_CLARIFICATION = "unclear_after_clarification"
    PROMPT_INJECTION = "prompt_injection"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    OUTPUT_VALIDATION_FAILED = "output_validation_failed"


class SafetyFlag(StrEnum):
    """Deterministic flags raised by the input or output guardrails."""

    CREDENTIAL_DISCLOSURE = "credential_disclosure"
    PROMPT_INJECTION = "prompt_injection"
    EMERGENCY = "emergency"
    THREAT = "threat"
    SELF_HARM = "self_harm"
    CYBERSECURITY = "cybersecurity"
    LEGAL_REQUEST = "legal_request"
    OUT_OF_SCOPE = "out_of_scope"
    UNSUPPORTED_CLAIM = "unsupported_claim"


class KnowledgeStatus(StrEnum):
    """Permitted local record statuses."""

    APPROVED = "approved"
    DEMO_ONLY = "demo_only"
    INACTIVE = "inactive"


class DraftStatus(StrEnum):
    """Lifecycle status of an in-memory complaint draft."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
