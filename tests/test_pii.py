"""Fail-closed privacy scanning with synthetic pattern fixtures."""

from __future__ import annotations

import pytest

from app.services.pii import (
    DerivedFixturePIIError,
    PIICategory,
    redact_likely_pii,
    scan_text,
    validate_derived_fixture,
)


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("email: synthetic.person@example.test", PIICategory.EMAIL),
        ("JSHSHIR: 12345678901234", PIICategory.JSHSHIR),
        ("IMEI: 123456789012345", PIICategory.IMEI),
        ("passport: AB 1234567", PIICategory.PASSPORT),
        ("phone: +998 90 123 45 67", PIICategory.PHONE_OR_SUBSCRIBER),
        ("full name: Synthetic Person", PIICategory.PERSON_NAME),
        ("address: Synthetic Street 1", PIICategory.ADDRESS),
        ("document no: SYN-12345", PIICategory.DOCUMENT_CODE),
        ("signature: Synthetic Signer", PIICategory.SIGNATURE),
    ],
)
def test_defined_pii_patterns_are_detected(text: str, category: PIICategory) -> None:
    assert category in {finding.category for finding in scan_text(text)}


def test_clean_anonymized_fixture_passes() -> None:
    fixture = {
        "category": "mnp",
        "subcategory": "general_process",
        "summary": "Synthetic transfer-process difficulty with no identifying values.",
        "prior_actions": ["Contacted a synthetic operator"],
    }

    validate_derived_fixture(fixture)


def test_sensitive_field_name_fails_even_when_value_is_opaque() -> None:
    with pytest.raises(DerivedFixturePIIError, match="sensitive_field"):
        validate_derived_fixture({"full_imei": "opaque-reference"})


def test_nested_pii_failure_does_not_echo_value() -> None:
    sensitive = "synthetic.person@example.test"

    with pytest.raises(DerivedFixturePIIError) as error:
        validate_derived_fixture({"scenario": {"notes": [sensitive]}})

    assert sensitive not in str(error.value)
    assert "email:1" in str(error.value)


def test_redaction_removes_values_without_reversible_tokens() -> None:
    sensitive = "synthetic.person@example.test"
    redacted = redact_likely_pii(f"email: {sensitive}")

    assert sensitive not in redacted
    assert "[redacted-email]" in redacted
