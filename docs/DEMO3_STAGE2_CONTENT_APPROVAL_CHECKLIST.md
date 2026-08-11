# Demo 3 Stage 2 Content Approval Checklist

## Mandatory decision sequence

1. Confirm the cited departmental paragraphs and current public evidence.
2. Resolve any requested source-verification gap; do not treat silence as support.
3. Record approve, reject, or request-changes for the Uzbek record.
4. Enter the reviewer's real name, position, timestamp, comments, and next review date.
5. Obtain independent legal review where the record names a legal-reviewer role.
6. Review Russian and English drafts separately against the approved Uzbek hash.
7. Do not activate a record as part of this checklist. Activation is a separate later
   control and is outside Stage 2.

The candidate JSON contains blank human-decision fields. Software must not populate
them. The following table is a paper-review index only.

| Candidate | Classification | Verification | Decision | Reviewer/position | Timestamp/comments |
| --- | --- | --- | --- | --- | --- |
| `IMEI-UZ-IDENTIFIER-FIND-001` | `imei` / `status_check` | `verified` |  |  |  |
| `IMEI-UZ-STATUS-CHECK-001` | `imei` / `status_check` | `verified` |  |  |  |
| `IMEI-UZ-REGISTRATION-METHODS-001` | `imei` / `registration_methods` | `verified` |  |  |  |
| `IMEI-UZ-RESIDENT-DECLARATION-001` | `imei` / `device_import` | `verified` |  |  |  |
| `IMEI-UZ-SUBSCRIBER-OWNERSHIP-001` | `imei` / `required_documents` | `verified` |  |  |  |
| `IMEI-UZ-POSTAL-IMPORT-001` | `imei` / `device_import` | `verified` |  |  |  |
| `IMEI-UZ-NONRESIDENT-REGISTRATION-001` | `imei` / `foreign_citizens` | `verified` |  |  |  |
| `IMEI-UZ-LOCAL-PURCHASE-001` | `imei` / `device_import` | `verified` |  |  |  |
| `IMEI-UZ-MULTIPLE-CODES-001` | `imei` / `dual_sim_multiple_imei` | `pending` |  |  |  |
| `IMEI-UZ-UNBLOCK-AFTER-REGISTRATION-001` | `imei` / `errors_support` | `pending` |  |  |  |
| `IMEI-UZ-LEGACY-CLONE-LINK-001` | `imei` / `errors_support` | `pending` |  |  |  |
| `IMEI-UZ-LOST-STOLEN-001` | `imei` / `errors_support` | `partially_verified` |  |  |  |
| `IMEI-UZ-CUSTOMS-EXCESS-001` | `imei` / `device_import` | `verified` |  |  |  |
| `IMEI-UZ-JSHSHIR-DEFINITION-001` | `imei` / `required_documents` | `verified` |  |  |  |
| `IMEI-UZ-TAC-MISMATCH-001` | `imei` / `errors_support` | `pending` |  |  |  |
| `IMEI-UZ-REGISTRATION-RESPONSIBILITY-001` | `imei` / `registration_eligibility` | `verified` |  |  |  |
| `IMEI-UZ-STATELESS-IDENTITY-001` | `imei` / `foreign_citizens` | `verified` |  |  |  |
| `IMEI-UZ-ONE-TIME-REGISTRATION-001` | `imei` / `registration_eligibility` | `pending` |  |  |  |
| `IMEI-UZ-TARIFF-INDIVIDUAL-WITHIN-30-001` | `imei` / `tariffs` | `verified` |  |  |  |
| `IMEI-UZ-TARIFF-INDIVIDUAL-AFTER-30-001` | `imei` / `tariffs` | `verified` |  |  |  |
| `IMEI-UZ-TARIFF-IMPORTER-001` | `imei` / `tariffs` | `verified` |  |  |  |
| `IMEI-UZ-TARIFF-MANUFACTURER-001` | `imei` / `tariffs` | `verified` |  |  |  |
| `IMEI-UZ-TARIFF-FOREIGN-ROAMING-001` | `imei` / `tariffs` | `verified` |  |  |  |
| `MNP-UZ-OPERATOR-LIST-001` | `mnp` / `operator_selection` | `verified` |  |  |  |
| `MNP-UZ-NUMBER-PRESERVATION-001` | `mnp` / `eligibility` | `verified` |  |  |  |
| `MNP-UZ-GSM-ONLY-001` | `mnp` / `eligibility` | `verified` |  |  |  |
| `MNP-UZ-RETRANSFER-INTERVAL-001` | `mnp` / `transfer_conditions` | `verified` |  |  |  |
| `MNP-UZ-BALANCE-TRANSFER-001` | `mnp` / `debt_balance` | `verified` |  |  |  |
| `MNP-UZ-TRANSFER-TIMING-001` | `mnp` / `transfer_timing` | `pending` |  |  |  |
| `MNP-UZ-PERSONAL-DATA-MATCH-001` | `mnp` / `transfer_conditions` | `verified` |  |  |  |
| `MNP-UZ-DEBT-CONDITION-001` | `mnp` / `debt_balance` | `verified` |  |  |  |
| `MNP-UZ-CONTRACT-OBLIGATION-001` | `mnp` / `transfer_conditions` | `pending` |  |  |  |
| `MNP-UZ-SUCCESS-SMS-001` | `mnp` / `status_check` | `verified` |  |  |  |
| `MNP-UZ-INDIVIDUAL-DOCUMENT-001` | `mnp` / `required_documents` | `verified` |  |  |  |
| `MNP-UZ-LEGAL-ENTITY-DOCUMENT-001` | `mnp` / `required_documents` | `pending` |  |  |  |
| `MNP-UZ-REJECTED-DATA-MISMATCH-001` | `mnp` / `rejected_transfer` | `pending` |  |  |  |
| `MNP-UZ-REJECTED-DEBT-001` | `mnp` / `rejected_transfer` | `verified` |  |  |  |
| `MNP-UZ-REJECTED-INTERVAL-001` | `mnp` / `rejected_transfer` | `verified` |  |  |  |
| `MNP-UZ-REJECTED-BLOCKED-001` | `mnp` / `rejected_transfer` | `pending` |  |  |  |
| `MNP-UZ-OWNER-REPRESENTATIVE-001` | `mnp` / `number_ownership` | `pending` |  |  |  |
| `MNP-UZ-OWNERSHIP-REASSIGNMENT-001` | `mnp` / `number_ownership` | `pending` |  |  |  |
| `MNP-UZ-ROAMING-DEBT-BLOCK-001` | `mnp` / `debt_balance` | `pending` |  |  |  |
| `MNP-UZ-APPLICATION-RECIPIENT-001` | `mnp` / `application_procedure` | `verified` |  |  |  |
| `MNP-UZ-SERVICE-FEE-001` | `mnp` / `service_fee` | `partially_verified` |  |  |  |
| `MNP-UZ-NEW-SIM-001` | `mnp` / `application_procedure` | `verified` |  |  |  |
| `MNP-UZ-DEFINITION-001` | `mnp` / `eligibility` | `verified` |  |  |  |

## Decision vocabulary

- Uzbek: `approve`, `reject`, or `request_changes`.
- Russian translation: separate `approve`, `reject`, or `request_changes`.
- English translation: separate `approve`, `reject`, or `request_changes`.
- Any unresolved conflict or missing named owner keeps the record ineligible.
