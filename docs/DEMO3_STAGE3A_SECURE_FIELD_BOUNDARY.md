# Demo 3 Stage 3A Secure-Field Boundary

## Protected values

Ordinary chat, drafts, logs, metrics, and responses may not hold raw passport details,
PINFL/JSHSHIR, full IMEI values, private telephone numbers, residential addresses,
personal email addresses, signatures, identity images, confidential attachments,
legal-entity registration identifiers, or representative authorization documents.

## Opaque reference

`SecureValueReference` contains only:

```json
{
  "reference_id": "random-uuid-v4",
  "field_type": "identity_document",
  "masked_display": "***",
  "storage_provider": "not_configured",
  "verified": false
}
```

UUIDv4 is required. The model has no raw-value, path, bucket, table, citizen ID,
document number, or verification-evidence field. Extra fields are rejected and the
masked display is fixed to `***`.

## Stage 3A implementation limit

`SecureValueIssuer` is an interface only. No production secure storage exists.
`SyntheticSecureValueIssuer` is a test double that accepts only values beginning with
an obvious synthetic marker, rejects likely PII, issues a fresh UUIDv4, and retains no
input value. Its `SecretStr` input and the returned reference are safe for accidental
string representation in tests.

The ordinary draft model independently scans its subject, issue description, and
occurrence values and rejects sensitive field names. Secure values must cross a future
approved secure boundary; they cannot be added to the draft dictionary.

## Decisions still required

RTMC must approve the data controller/processor roles, lawful basis, data minimization,
retention/deletion, encryption and key management, storage jurisdiction, access model,
audit trail, incident response, attachment malware scanning, redaction, and subject
rights before any real secure provider is designed or selected.
