"""Audit log and the /assistant/metrics KPI endpoint."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.audit_log import (
    OUTCOME_HANDOFF,
    OUTCOME_RESOLVED,
    AuditEvent,
    InMemoryAuditLog,
)


def _event(outcome: str, category: str) -> AuditEvent:
    return AuditEvent(channel="web", language="uz", outcome=outcome, category=category)


def test_inmemory_log_computes_resolution_rate() -> None:
    log = InMemoryAuditLog()
    asyncio.run(log.record(_event(OUTCOME_RESOLVED, "imei")))
    asyncio.run(log.record(_event(OUTCOME_RESOLVED, "imei")))
    asyncio.run(log.record(_event(OUTCOME_HANDOFF, "mnp")))
    metrics = asyncio.run(log.metrics())
    assert metrics["total_events"] == 3
    assert metrics["terminal_events"] == 3
    assert metrics["self_service_resolution_rate"] == round(2 / 3, 4)
    assert metrics["handoff_rate"] == round(1 / 3, 4)
    assert metrics["categories"] == {"imei": 2, "mnp": 1}


def test_empty_log_reports_no_rate() -> None:
    metrics = asyncio.run(InMemoryAuditLog().metrics())
    assert metrics["total_events"] == 0
    assert metrics["self_service_resolution_rate"] is None


def test_metrics_endpoint_reflects_diagnose_turns() -> None:
    with TestClient(create_app()) as client:
        # Intermediate question.
        client.post("/assistant/diagnose", json={"message": "telefonim bloklandi"})
        # Reach a resolution card.
        client.post(
            "/assistant/diagnose",
            json={
                "message": "not_registered",
                "tree_id": "imei-blokdan_chiqarish",
                "node_id": "cause",
            },
        )
        # Vague problem -> routing menu (clarify).
        client.post("/assistant/diagnose", json={"message": "telefonim ishlamayapti"})

        metrics = client.get("/assistant/metrics").json()

    assert metrics["total_events"] == 3
    outcomes = metrics["outcomes"]
    assert outcomes.get("resolved", 0) >= 1
    assert outcomes.get("question", 0) >= 1
    assert outcomes.get("clarify", 0) >= 1
    assert metrics["categories"].get("imei", 0) >= 1
