"""Case reasoning phase 1: fact extraction, CaseState and /assistant/understand."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus
from app.domain.diagnostics import DiagnosticNode, ResolutionCard
from app.main import create_app
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.fact_extraction import LLMFactExtractor, RuleBasedFactExtractor

_DIAGNOSTICS = Path(__file__).resolve().parents[1] / "app" / "data" / "diagnostics.json"

_DUBAI_STORY = (
    "Dubaydan telefon olib kelgandim ikki oycha bo'ldi. Avval ishlayotgandi, "
    "keyin ikkinchi sim tarmoqni ko'rmay qoldi. IMEI haqida SMS ham kelgandi. "
    "Saytda nimadir qilib ko'rdim, lekin bo'lmadi."
)


def _case() -> CaseState:
    return CaseState(case_id="c1", session_id="s1", domain="imei")


def test_rule_extractor_reconstructs_dubai_case() -> None:
    extracted = asyncio.run(RuleBasedFactExtractor().extract(_DUBAI_STORY, _case(), turn_id=1))
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


def test_llm_extractor_merges_and_prefers_rule_matches() -> None:
    async def fake_complete(prompt: str) -> str:
        return json.dumps(
            {
                "facts": [
                    # Rules already say imported; the LLM's weaker guess must not win.
                    {"name": "device_origin", "value": "local", "status": "inferred",
                     "confidence": 0.6},
                    # A fact the rules missed is added.
                    {"name": "declaration_status", "value": "not_declared",
                     "status": "explicit", "confidence": 0.9},
                ]
            }
        )

    extractor = LLMFactExtractor(fake_complete, fallback=RuleBasedFactExtractor())
    facts = {f.name: f for f in asyncio.run(extractor.extract(_DUBAI_STORY, _case(), turn_id=1))}
    assert facts["device_origin"].value == "imported"  # rule match kept
    assert facts["declaration_status"].value == "not_declared"  # LLM added
    assert facts["declaration_status"].source == "llm"


def test_llm_extractor_falls_back_to_rules_on_error() -> None:
    async def broken(prompt: str) -> str:
        raise RuntimeError("network down")

    extractor = LLMFactExtractor(broken, fallback=RuleBasedFactExtractor())
    facts = {f.name for f in asyncio.run(extractor.extract(_DUBAI_STORY, _case(), turn_id=1))}
    assert "device_origin" in facts  # rule facts still returned


def test_llm_extractor_rejects_invalid_or_unknown_facts() -> None:
    async def fake(prompt: str) -> str:
        return json.dumps(
            {
                "facts": [
                    {"name": "affected_sim", "value": "third", "status": "explicit",
                     "confidence": 0.9},  # invalid value -> rejected (rule keeps 'second')
                    {"name": "made_up_field", "value": "x", "status": "explicit",
                     "confidence": 1.0},  # unknown fact -> rejected
                ]
            }
        )

    extractor = LLMFactExtractor(fake, fallback=RuleBasedFactExtractor())
    extracted = asyncio.run(extractor.extract(_DUBAI_STORY, _case(), turn_id=1))
    facts = {f.name: f.value for f in extracted}
    assert facts["affected_sim"] == "second"
    assert "made_up_field" not in facts


def test_walk_asks_only_the_unknown_fact() -> None:
    engine = DiagnosticEngine.from_json(_DIAGNOSTICS)
    tree = "imei-royxatdan_otkazish"

    kind, node = engine.walk(tree, {})
    assert kind == "ask" and isinstance(node, DiagnosticNode) and node.id == "source"

    # device_origin known -> the 'where from' question is skipped.
    kind, node = engine.walk(tree, {"device_origin": "imported"})
    assert kind == "ask" and isinstance(node, DiagnosticNode) and node.id == "customs"

    # Enough facts -> resolve without any question.
    kind, card = engine.walk(
        tree, {"device_origin": "imported", "declaration_status": "not_declared"}
    )
    assert kind == "resolve" and isinstance(card, ResolutionCard) and card.id == "imei-customs"


def test_converse_dubai_skips_known_facts_then_resolves() -> None:
    with TestClient(create_app()) as client:
        turn1 = client.post(
            "/assistant/converse",
            json={"message": _DUBAI_STORY, "session_id": "cv1", "language": "uz"},
        ).json()
        assert turn1["done"] is False
        assert turn1["known_facts"]["device_origin"] == "imported"  # understood, not asked
        assert "me'yor" in turn1["reply"] or "deklarat" in turn1["reply"].lower()

        turn2 = client.post(
            "/assistant/converse",
            json={"message": "Deklaratsiya qilmaganman", "session_id": "cv1", "language": "uz"},
        ).json()
        assert turn2["done"] is True
        assert turn2["card_id"] == "imei-customs"


def test_converse_greets_small_talk_without_a_menu() -> None:
    with TestClient(create_app()) as client:
        body = client.post(
            "/assistant/converse",
            json={"message": "hello", "session_id": "cv-greet", "language": "uz"},
        ).json()
        assert body["done"] is False
        assert body["card_id"] is None
        assert body["options"] == []  # a greeting, not the routing menu
        assert body["requires_human"] is False


def test_converse_routes_mnp_to_a_domain_menu() -> None:
    with TestClient(create_app()) as client:
        body = client.post(
            "/assistant/converse",
            json={"message": "Menga MNP bo'yicha muammo bor", "session_id": "cv-mnp"},
        ).json()
        assert body["domain"] == "mnp"
        assert body["done"] is False
        values = {opt["value"] for opt in body["options"]}
        assert values and all(v.startswith("mnp-") for v in values)  # only MNP topics offered


def test_converse_new_problem_after_resolve_does_not_reuse_facts() -> None:
    with TestClient(create_app()) as client:
        # Resolve a customs case first.
        client.post(
            "/assistant/converse",
            json={"message": _DUBAI_STORY, "session_id": "cv-reuse", "language": "uz"},
        )
        done = client.post(
            "/assistant/converse",
            json={"message": "Deklaratsiya qilmaganman", "session_id": "cv-reuse"},
        ).json()
        assert done["done"] is True and done["card_id"] == "imei-customs"

        # A brand-new problem must start fresh, not auto-resolve on the old facts.
        fresh = client.post(
            "/assistant/converse",
            json={"message": "Qurilmani ro'yxatdan o'tkazmoqchiman", "session_id": "cv-reuse"},
        ).json()
        assert fresh["done"] is False  # asks, not silently reuses declaration_status
        assert "declaration_status" not in fresh["known_facts"]


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
