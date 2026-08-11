# Demo 3 Stage 3C Orchestration

## Internal facade

`GovernedComplaintOrchestrator` runs the following server-owned sequence:

1. Require an explicit supported language or return language selection.
2. Apply deterministic safety and PII checks.
3. Apply deterministic scope checks and current-request-only refusal.
4. Determine applicant type, appeal kind, category, and compatible subcategory from explicit structured values or closed multilingual rules.
5. Select a versioned provisional requirements profile.
6. Create or edit the single canonical governed draft through the Stage 3B adapter.
7. Calculate missing ordinary and secure fields.
8. Select one versioned, same-language follow-up question.
9. Return typed human handoff where policy requires it.
10. Generate a non-sensitive governed review.
11. Require acknowledgement of the exact review version and hash.
12. Bind consent and stop locally at `submission_blocked`.

The facade has no provider dependency and no official-system client.

## Classification and profiles

Applicant type and appeal kind remain independent of category and subcategory. Unknown values remain unknown and trigger clarification. Repeatedly unclear requests trigger typed human handoff.

The technical subcategories `number_code_information`, `network_service_degradation`, `website_functional_error`, and `other_rtmc_matter` exist only to make deterministic internal state valid. They are not legal classifications and do not claim organizational approval.

## Structured questions

Follow-up keys are qualified by `synthetic-stage3c-follow-up-v1`. One question is returned at a time. Network questions cover operator, service type, region, district/city, approximate location, occurrence time, frequency, duration, and impact. Approximate-location wording explicitly excludes a residential address.

## Review and consent

The internal review contains applicant/appeal/category/subcategory, subject, structured description, occurrence details, masked secure-field indicators, missing fields, human-review state, draft/session IDs, version, canonical hash, language, notice and consent wording versions, and an explicit non-registration notice.

Secure reference IDs and raw values are not shown. Consent requires the exact reviewed draft ID, synthetic session identity, version, canonical hash, language, notice version, wording version, and timezone-aware timestamp. An edit creates a new version/hash and invalidates prior consent.

The only terminal consent result is `submission_blocked`; `officially_registered=false`, `case_number=null`, and `official_status=null` remain invariant.
