"""Conservative PII detection for confidential derivation gates."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class PIICategory(StrEnum):
    """Sensitive identifiers defined by the Demo 3 handling policy."""

    PERSON_NAME = "person_name"
    ADDRESS = "address"
    PHONE_OR_SUBSCRIBER = "phone_or_subscriber"
    EMAIL = "email"
    JSHSHIR = "jshshir"
    PASSPORT = "passport"
    IMEI = "imei"
    DOCUMENT_CODE = "document_code"
    SIGNATURE = "signature"
    SENSITIVE_FIELD = "sensitive_field"


@dataclass(frozen=True, slots=True)
class PIIFinding:
    """Location-only finding; the sensitive value is deliberately omitted."""

    category: PIICategory
    start: int
    end: int


class DerivedFixturePIIError(ValueError):
    """A derived artifact contains likely PII and must not be committed."""


_PATTERNS: tuple[tuple[PIICategory, re.Pattern[str]], ...] = (
    (
        PIICategory.EMAIL,
        re.compile(
            r"(?i)(?<![\w.+-])[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+(?![\w.-])"
        ),
    ),
    (PIICategory.JSHSHIR, re.compile(r"(?<!\d)\d{14}(?!\d)")),
    (PIICategory.IMEI, re.compile(r"(?<!\d)\d{15}(?!\d)")),
    (
        PIICategory.PASSPORT,
        re.compile(
            r"(?i)(?:passport|паспорт|pasport)\s*(?:no\.?|№|raqami)?\s*[:=-]?\s*[a-z]{2}\s*\d{7}"
        ),
    ),
    (
        PIICategory.PHONE_OR_SUBSCRIBER,
        re.compile(r"(?<!\d)(?:\+?998[\s()-]*)\d{2}[\s()-]*\d{3}[\s()-]*\d{2}[\s()-]*\d{2}(?!\d)"),
    ),
    (
        PIICategory.PERSON_NAME,
        re.compile(
            r"(?i)(?:full\s+name|first\s+name|last\s+name|surname|f\.?i\.?o\.?|"
            r"фамили[яи]|имя|фио|to['’]?liq\s+ism|familiya|ism)\s*[:=-]\s*"
            r"[^\n,;]{2,100}"
        ),
    ),
    (
        PIICategory.ADDRESS,
        re.compile(
            r"(?i)(?:home\s+address|postal\s+address|residence|address|адрес|манзил|yashash\s+joyi)"
            r"\s*[:=-]\s*[^\n;]{3,160}"
        ),
    ),
    (
        PIICategory.DOCUMENT_CODE,
        re.compile(
            r"(?i)(?:document|reference|hujjat|ma['’]?lumotnoma|документ)\s*"
            r"(?:no\.?|№|raqami)?\s*[:=-]\s*[a-z0-9/-]{5,40}"
        ),
    ),
    (
        PIICategory.SIGNATURE,
        re.compile(r"(?i)(?:signature|signed\s+by|подпись|imzo)\s*[:=-]\s*[^\n;]{2,100}"),
    ),
)

_SENSITIVE_KEYS = frozenset(
    {
        "address",
        "attachments",
        "email",
        "full_imei",
        "full_name",
        "identity",
        "jshshir",
        "passport",
        "phone",
        "pinfl",
        "residence",
        "signature",
        "subscriber_number",
    }
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_KEY_MARKERS = (
    "attachment",
    "authorization_document",
    "document_image",
    "email",
    "full_imei",
    "identity_document",
    "jshshir",
    "passport",
    "personal_email",
    "phone",
    "pinfl",
    "private_telephone",
    "registration_identifier",
    "residential_address",
    "signature",
)


def is_sensitive_field_name(value: str) -> bool:
    """Return whether an ordinary-storage key is reserved for protected data."""
    normalized = value.strip().casefold()
    return normalized in _SENSITIVE_KEYS or any(
        marker in normalized for marker in _SENSITIVE_KEY_MARKERS
    )


def scan_text(text: str) -> tuple[PIIFinding, ...]:
    """Return categories and offsets only, never captured sensitive text."""
    findings: list[PIIFinding] = []
    for category, pattern in _PATTERNS:
        findings.extend(
            PIIFinding(category=category, start=match.start(), end=match.end())
            for match in pattern.finditer(text)
        )
    return tuple(
        sorted(findings, key=lambda finding: (finding.start, finding.end, finding.category))
    )


def redact_likely_pii(text: str) -> str:
    """Replace detected spans without retaining reversible values or tokens."""
    findings = scan_text(text)
    if not findings:
        return text
    redacted: list[str] = []
    cursor = 0
    for finding in findings:
        if finding.end <= cursor:
            continue
        start = max(cursor, finding.start)
        redacted.append(text[cursor:start])
        redacted.append(f"[redacted-{finding.category.value}]")
        cursor = finding.end
    redacted.append(text[cursor:])
    return "".join(redacted)


def scan_derived_fixture(value: object) -> tuple[PIIFinding, ...]:
    """Scan nested JSON-like data and reject secure-field names as well as values."""
    findings: list[PIIFinding] = []

    def visit(item: object) -> None:
        if isinstance(item, str):
            findings.extend(scan_text(item))
            return
        if isinstance(item, Mapping):
            for key, nested in item.items():
                normalized_key = str(key).strip().casefold()
                if is_sensitive_field_name(normalized_key):
                    findings.append(PIIFinding(PIICategory.SENSITIVE_FIELD, 0, 0))
                if (
                    normalized_key.endswith("_sha256")
                    and isinstance(nested, str)
                    and _SHA256_PATTERN.fullmatch(nested)
                ):
                    continue
                visit(nested)
            return
        if isinstance(item, Sequence) and not isinstance(item, bytes | bytearray):
            for nested in item:
                visit(nested)

    visit(value)
    return tuple(findings)


def validate_derived_fixture(value: object) -> None:
    """Fail closed with category counts and without echoing any source value."""
    findings = scan_derived_fixture(value)
    if not findings:
        return
    counts: dict[PIICategory, int] = {}
    for finding in findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    summary = ",".join(f"{category.value}:{counts[category]}" for category in sorted(counts))
    raise DerivedFixturePIIError(f"derived_fixture_contains_likely_pii:{summary}")
