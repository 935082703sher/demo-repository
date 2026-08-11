"""Stage 3A secure-value interface and a synthetic, non-retaining test double."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from pydantic import SecretStr

from app.domain.complaint_workflow import (
    SecureFieldType,
    SecureStorageProvider,
    SecureValueReference,
)
from app.services.pii import scan_text


class SecureValueIssuer(Protocol):
    """Future secure-storage seam; implementations return only an opaque reference."""

    def issue_reference(
        self,
        *,
        field_type: SecureFieldType,
        synthetic_value: SecretStr,
    ) -> SecureValueReference:
        """Accept a protected value at the secure boundary and return metadata only."""
        ...


class SyntheticSecureValueIssuer:
    """Test double that accepts obvious synthetic markers and retains no value."""

    _prefix = "SYNTHETIC_TEST_VALUE_"

    def issue_reference(
        self,
        *,
        field_type: SecureFieldType,
        synthetic_value: SecretStr,
    ) -> SecureValueReference:
        """Reject likely real PII, issue UUIDv4, and immediately discard the input."""
        value = synthetic_value.get_secret_value()
        if not value.startswith(self._prefix) or scan_text(value):
            raise ValueError("synthetic_secure_value_required")
        return SecureValueReference(
            reference_id=uuid4(),
            field_type=field_type,
            masked_display="***",
            storage_provider=SecureStorageProvider.SYNTHETIC_MEMORY,
            verified=False,
        )
