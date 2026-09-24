"""Interaction log: JSONL capture and PII-safe converse recording."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.interaction_log import (
    InteractionRecord,
    JsonlInteractionLog,
    NullInteractionLog,
    build_interaction_log,
    read_records,
)


def test_jsonl_log_appends_and_reads_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "interactions.jsonl"
    log = JsonlInteractionLog(path)
    asyncio.run(log.record(InteractionRecord(
        session_id="s", channel="web", language="uz", message="salom", reply="Assalomu",
        outcome="greeting",
    )))
    asyncio.run(log.record(InteractionRecord(
        session_id="s", channel="web", language="uz", message="rahmat", reply="Xayr",
        outcome="greeting",
    )))
    rows = read_records(path)
    assert len(rows) == 2
    assert rows[0]["message"] == "salom" and rows[0]["outcome"] == "greeting"


def test_build_interaction_log_defaults_to_null() -> None:
    assert isinstance(build_interaction_log(None), NullInteractionLog)


def test_converse_logs_a_redacted_turn(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "log.jsonl"
    settings = Settings(_env_file=None, environment="test", interaction_log_path=str(path))
    with TestClient(create_app(settings=settings)) as client:
        client.post(
            "/assistant/converse",
            json={
                "message": "IMEI 356938035643809 ro'yxatdan o'tmayapti",
                "session_id": "log-1",
            },
        )
    rows = read_records(path)
    assert len(rows) == 1
    row = rows[0]
    assert "356938035643809" not in row["message"]  # PII redacted before logging
    assert row["reply"] and row["outcome"] in {"question", "menu", "resolved", "answer"}
    assert row["session_id"] == "log-1"


def test_feedback_endpoint_records_rating(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "log.jsonl"
    settings = Settings(_env_file=None, environment="test", interaction_log_path=str(path))
    with TestClient(create_app(settings=settings)) as client:
        body = client.post(
            "/assistant/feedback",
            json={"session_id": "fb-1", "helpful": False, "card_id": "imei-customs"},
        ).json()
        assert body["ok"] is True and body["reply"]
    rows = read_records(path)
    fb = [r for r in rows if r["kind"] == "feedback"]
    assert len(fb) == 1
    assert fb[0]["feedback"] == "unhelpful" and fb[0]["card_id"] == "imei-customs"


def test_converse_stream_also_logs_once(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "log.jsonl"
    settings = Settings(_env_file=None, environment="test", interaction_log_path=str(path))
    with TestClient(create_app(settings=settings)) as client:
        client.post(
            "/assistant/converse/stream",
            json={"message": "salom", "session_id": "log-2"},
        )
    rows = read_records(path)
    assert len(rows) == 1 and rows[0]["outcome"] == "greeting"
