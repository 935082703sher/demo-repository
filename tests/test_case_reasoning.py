"""Case reasoning phase 1: fact extraction, CaseState and /assistant/understand."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus
from app.main import create_app
from app.services.fact_extraction import RuleBasedFactExtractor

_DUBAI_STORY = (
    "Dubaydan telefon olib kelgandim ikki oycha bo'ldi. Avval ishlayotgandi, "
    "keyin ikkinchi sim tarmoqni ko'rmay qoldi. IMEI haqida SMS ham kelgandi. "
    "Saytda nimadir qilib ko'rdim, lekin bo'lmadi."
)


def _case() -> CaseState:
    return CaseState(case_id="c1", session_id="s1", domain="imei")


def test_rule_extractor_reconstructs_dubai_case() -> None:
    extracted = RuleBasedFactExtractor().extract(_DUBAI_STORY, _case(), turn_id=1)
    facts = {f.name: f.value for f in extracted}
    assert facts["device_origin"] == "imported"
    assert facts["origin_country"] == "UAE"
    assert facts["previously_working"] == "true"
    assert facts["affected_sim"] == "second"
    assert facts["imei_notification_received"] == "true"
    assert facts["registration_status"] == "failed"
    # Never invented: declaration was not mentioned.
    assert "declaration_status" not in facts


def test_casestate_upsert_keeps_explicit_over_inferred() -> None:
    case = _case()
    case.upsert(Fact(name="device_origin", value="imported", status=FactStatus.EXPLICIT))
    case.upsert(Fact(name="device_origin", value="local", status=FactStatus.INFERRED))
    assert case.facts["device_origin"].value == "imported"  # inference did not override
    case.upsert(Fact(name="device_origin", value="local", status=FactStatus.VERIFIED))
    assert case.facts["device_origin"].value == "local"  # a stronger status may


def test_understand_endpoint_extracts_and_persists_across_turns() -> None:
    with TestClient(create_app()) as client:
        first = client.post(
            "/assistant/understand",
            json={"message": _DUBAI_STORY, "session_id": "sess-1", "language": "uz"},
        ).json()
        assert first["domain"] == "imei"
        assert first["known_facts"]["device_origin"] == "imported"
        assert first["known_facts"]["affected_sim"] == "second"
        # declaration_status is decision-critical but still unknown.
        assert "declaration_status" in first["unknown_facts"]
        assert first["turn_count"] == 1

        # Next turn answers the missing fact; the case keeps prior facts.
        second = client.post(
            "/assistant/understand",
            json={"message": "Deklaratsiya qilmaganman", "session_id": "sess-1", "language": "uz"},
        ).json()
        assert second["turn_count"] == 2
        assert second["domain"] == "imei"  # domain persisted
        assert second["known_facts"]["device_origin"] == "imported"  # earlier fact kept
        assert second["known_facts"]["declaration_status"] == "not_declared"
        assert "declaration_status" not in second["unknown_facts"]


def test_understand_reports_unknowns_for_short_message() -> None:
    with TestClient(create_app()) as client:
        body = client.post(
            "/assistant/understand",
            json={"message": "IMEI muammosi bor", "session_id": "sess-2", "language": "uz"},
        ).json()
        assert body["domain"] == "imei"
        # A vague message yields mostly unknowns, and invents nothing.
        assert body["known_facts"] == {} or "device_origin" not in body["known_facts"]
        assert "device_origin" in body["unknown_facts"]
        assert body["status"] == CaseStatus.UNDERSTANDING.value
