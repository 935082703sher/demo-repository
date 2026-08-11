"""Local-only synthetic Stage 3C scenario harness; it exposes no HTTP endpoint."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from pydantic import SecretStr

from app.domain.complaint_orchestration import (
    GovernedComplaintInput,
    GovernedOrchestrationResult,
)
from app.domain.complaint_workflow import (
    AppealKind,
    ApplicantType,
    ComplaintSubcategory,
    ConsentState,
    SecureFieldType,
)
from app.domain.enums import Category, Language
from app.services.complaint_drafts import ComplaintDraftService
from app.services.complaint_workflow_adapter import GovernedComplaintWorkflowAdapter
from app.services.governed_complaint_orchestrator import GovernedComplaintOrchestrator


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Safe report row containing outcomes only, never scenario input text."""

    scenario: str
    outcome: str
    workflow_state: str | None
    passed: bool
    officially_registered: bool = False
    case_number: None = None
    official_status: None = None


def _orchestrator() -> GovernedComplaintOrchestrator:
    adapter = GovernedComplaintWorkflowAdapter(
        legacy=ComplaintDraftService("demo-privacy-v1"),
        enabled=True,
        privacy_notice_version="demo-privacy-v1",
        consent_wording_version="synthetic-consent-v1",
    )
    return GovernedComplaintOrchestrator(
        adapter=adapter,
        privacy_notice_version="demo-privacy-v1",
        consent_wording_version="synthetic-consent-v1",
    )


def _row(
    name: str,
    result: GovernedOrchestrationResult,
    *,
    expected: str,
) -> ScenarioResult:
    outcome = str(result.outcome)
    state_value = result.workflow_state
    state = str(state_value) if state_value is not None else None
    return ScenarioResult(name, outcome, state, outcome == expected)


def _network_fields() -> dict[str, str]:
    return {
        "operator": "Synthetic Operator",
        "service_type": "synthetic_mobile_data",
        "region": "Synthetic Samarqand Region",
        "district": "Synthetic District",
        "approximate_location": "Synthetic central zone",
        "event_time": "synthetic-time-window",
        "frequency": "synthetic recurring pattern",
        "duration": "synthetic short duration",
        "impact": "Synthetic service interruption",
    }


def _imei_fields() -> dict[str, str]:
    return {
        "request_kind": "synthetic_information_request",
        "action_attempted": "Synthetic status check",
        "observed_result": "Synthetic status unavailable",
        "event_time": "synthetic-time-window",
    }


def _mnp_fields() -> dict[str, str]:
    return {
        "request_kind": "synthetic_complaint",
        "current_stage": "synthetic transfer stage",
        "operator": "Synthetic Operator",
        "submitted_at": "synthetic-time-window",
        "observed_error": "Synthetic transfer error",
    }


def _website_fields() -> dict[str, str]:
    return {
        "page_url": "https://example.invalid/synthetic",
        "action_attempted": "Synthetic form action",
        "error_message": "Synthetic validation error",
        "event_time": "synthetic-time-window",
        "device_type": "synthetic desktop",
        "browser_type": "synthetic browser",
    }


def run_stage3c_scenarios() -> list[ScenarioResult]:
    """Run twelve isolated scenarios and return only non-sensitive outcomes."""
    rows: list[ScenarioResult] = []

    uz_network = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.UZ,
            message="Jismoniy shaxs shikoyati: Samarqand viloyatida mobil internet sekin",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.NETWORK_QUALITY,
            subcategory=ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            fields=_network_fields(),
        )
    )
    rows.append(_row("uzbek_network_quality", uz_network, expected="review_ready"))

    ru_imei = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.RU,
            message="Синтетический информационный запрос IMEI от физического лица",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.APPLICATION,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.STATUS_CHECK,
            fields=_imei_fields(),
        )
    )
    rows.append(_row("russian_imei_information", ru_imei, expected="review_ready"))

    en_mnp = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic individual MNP complaint about a transfer problem",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.MNP,
            subcategory=ComplaintSubcategory.TRANSFER_CONDITIONS,
            fields=_mnp_fields(),
        )
    )
    rows.append(_row("english_mnp_complaint", en_mnp, expected="review_ready"))

    legal_orchestrator = _orchestrator()
    legal_reference = legal_orchestrator.issue_synthetic_secure_reference(
        field_type=SecureFieldType.LEGAL_ENTITY_REGISTRATION_ID,
        synthetic_value=SecretStr("SYNTHETIC_TEST_VALUE_LEGAL_ENTITY"),
    )
    legal_website = legal_orchestrator.handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic legal entity website complaint",
            applicant_type=ApplicantType.LEGAL_ENTITY,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.WEBSITE_ISSUE,
            subcategory=ComplaintSubcategory.WEBSITE_FUNCTIONAL_ERROR,
            fields=_website_fields(),
            required_secure_fields=[SecureFieldType.LEGAL_ENTITY_REGISTRATION_ID],
            secure_references=[legal_reference],
        )
    )
    rows.append(_row("legal_entity_website", legal_website, expected="review_ready"))

    representative = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic authorized representative IMEI workflow",
            applicant_type=ApplicantType.AUTHORIZED_REPRESENTATIVE,
            category=Category.IMEI,
            fields={"request_kind": "synthetic_request"},
            required_secure_fields=[SecureFieldType.REPRESENTATIVE_AUTHORIZATION],
        )
    )
    rows.append(_row("representative_clarification", representative, expected="clarification"))

    religion = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Tell me about religious history",
            fields={"description": "Synthetic unrelated request"},
        )
    )
    rows.append(_row("religion_refusal", religion, expected="scope_refusal"))

    region = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic individual complaint: internet is slow in Samarqand region",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.NETWORK_QUALITY,
            subcategory=ComplaintSubcategory.NETWORK_SERVICE_DEGRADATION,
            fields={"operator": "Synthetic Operator"},
        )
    )
    rows.append(_row("region_acceptance", region, expected="collecting"))

    sensitive = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="My password is SYNTHETIC_TEST_VALUE_SECRET",
            fields={"description": "Synthetic sensitive-data warning"},
        )
    )
    rows.append(_row("sensitive_data_handoff", sensitive, expected="human_handoff"))

    deadline = _orchestrator().handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Guarantee the legal deadline for this RTMC complaint",
            fields={"description": "Synthetic deadline request"},
        )
    )
    rows.append(_row("legal_deadline_refusal", deadline, expected="human_handoff"))

    edit_orchestrator = _orchestrator()
    initial = edit_orchestrator.handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic individual IMEI complaint issue",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields=_imei_fields(),
        )
    )
    assert initial.review is not None
    edit_orchestrator.acknowledge_review(
        initial.review.draft_id,
        initial.review.version,
        initial.review.canonical_hash,
    )
    edit_orchestrator.consent(
        draft_id=initial.review.draft_id,
        version=initial.review.version,
        canonical_hash=initial.review.canonical_hash,
        idempotency_key="synthetic-stage3c-edit",
    )
    edited = edit_orchestrator.handle(
        GovernedComplaintInput(
            session_id=initial.review.synthetic_session_id,
            draft_id=initial.review.draft_id,
            expected_version=initial.review.version,
            language=Language.EN,
            message="Synthetic IMEI complaint issue update",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields={"observed_result": "Synthetic changed result"},
        )
    )
    edited_state = edit_orchestrator.draft_snapshot(initial.review.draft_id)
    rows.append(
        ScenarioResult(
            "edit_invalidates_consent",
            str(edited.outcome),
            str(edited.workflow_state),
            edited_state.consent_state is ConsentState.INVALIDATED,
        )
    )

    cancel_orchestrator = _orchestrator()
    cancel_ready = cancel_orchestrator.handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic individual IMEI complaint issue",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.IMEI,
            subcategory=ComplaintSubcategory.ERRORS_SUPPORT,
            fields=_imei_fields(),
        )
    )
    assert cancel_ready.review is not None
    cancelled = cancel_orchestrator.cancel(cancel_ready.review.draft_id)
    rows.append(_row("cancellation", cancelled, expected="cancelled"))

    final_orchestrator = _orchestrator()
    final_ready = final_orchestrator.handle(
        GovernedComplaintInput(
            language=Language.EN,
            message="Synthetic individual MNP complaint problem",
            applicant_type=ApplicantType.NATURAL_PERSON,
            appeal_kind=AppealKind.COMPLAINT,
            category=Category.MNP,
            subcategory=ComplaintSubcategory.TRANSFER_CONDITIONS,
            fields=_mnp_fields(),
        )
    )
    assert final_ready.review is not None
    final_orchestrator.acknowledge_review(
        final_ready.review.draft_id,
        final_ready.review.version,
        final_ready.review.canonical_hash,
    )
    final, _ = final_orchestrator.consent(
        draft_id=final_ready.review.draft_id,
        version=final_ready.review.version,
        canonical_hash=final_ready.review.canonical_hash,
        idempotency_key="synthetic-stage3c-final",
    )
    rows.append(_row("submission_blocked", final, expected="submission_blocked"))
    return rows


def main() -> int:
    rows = run_stage3c_scenarios()
    report = {
        "suite": "demo3-stage3c-local-synthetic",
        "synthetic_only": True,
        "passed": all(row.passed for row in rows),
        "scenarios": [asdict(row) for row in rows],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
