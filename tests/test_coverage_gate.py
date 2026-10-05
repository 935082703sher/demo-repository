"""Tree coverage gate: a specific sub-issue must not fall into a generic tree root.

Regression for: "Ikkinchi IMEI'ni ro'yxatdan o'tkaza olmayapman" was answered with
the generic registration root "Qurilmani qayerdan oldingiz?". It must instead enter
a tree that actually covers the second-IMEI case (or, if none did, the knowledge
base, then 1170) - never the generic root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.fact_extraction import specific_issue

_ENGINE = DiagnosticEngine.from_json(Path("app/data/diagnostics.json"))


def _post(client: TestClient, message: str, session: str) -> dict[str, Any]:
    return dict(
        client.post("/assistant/converse", json={"message": message, "session_id": session}).json()
    )


# --- unit: issue extraction and coverage lookup ---


def test_specific_issue_detects_second_imei_registration() -> None:
    assert specific_issue("Ikkinchi IMEIni ro'yxatdan o'tkaza olmayapman") == (
        "secondary_imei_registration"
    )
    assert specific_issue("birinchi imei ishlaydi, ikkinchisi ro'yxatdan o'tmayapti") == (
        "secondary_imei_registration"
    )
    assert specific_issue("cannot register the second imei") == "secondary_imei_registration"
    assert specific_issue("второй IMEI не регистрируется") == "secondary_imei_registration"


def test_specific_issue_ignores_non_registration_dual_sim_and_generic() -> None:
    # A dual-SIM network complaint with no registration intent is NOT this issue.
    assert specific_issue("ikkinchi sim tarmoqni ko'rmay qoldi, imei haqida sms keldi") is None
    # A plain registration message is not the specific second-IMEI issue.
    assert specific_issue("telefonim ro'yxatdan o'tmayapti") is None


def test_tree_covering_resolves_only_declared_issues() -> None:
    covering = _ENGINE.tree_covering("secondary_imei_registration")
    assert covering is not None and covering.id == "imei-ikkinchi_imei"
    assert _ENGINE.tree_covering("no_such_issue") is None
    assert _ENGINE.tree_covering(None) is None


# --- integration: the gate in the real conversation flow ---


def test_second_imei_does_not_enter_generic_registration_root() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "Ikkinchi IMEIni ro'yxatdan o'tkaza olmayapman", "gate-b")
        reply = body["reply"].lower()
        assert "qayerdan" not in reply  # NOT the generic "where did you get it" root
        assert "deklarat" in reply  # asks the declaration question that decides it
        values = {o["value"] for o in body["options"]}
        assert values == {"both", "one", "unknown"}
        assert body["done"] is False


def test_generic_registration_still_uses_its_root() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "IMEIni ro'yxatdan o'tkaza olmayapman", "gate-a")
        # A generic "can't register" (no second-IMEI marker) legitimately asks source.
        assert "qayerdan" in body["reply"].lower()
        assert body["done"] is False


def test_first_works_second_fails_routes_to_second_imei() -> None:
    with TestClient(create_app()) as client:
        body = _post(client, "Birinchi IMEI ishlaydi, ikkinchisi ro'yxatdan o'tmayapti", "gate-c")
        reply = body["reply"].lower()
        assert "qayerdan" not in reply
        assert "deklarat" in reply  # second-IMEI declaration question, not first-IMEI status
