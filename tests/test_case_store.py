"""Case store: async in-memory behaviour and the JSON roundtrip Postgres uses."""

from __future__ import annotations

import asyncio

from app.domain.case_state import CaseState, Fact, FactStatus
from app.services.case_store import InMemoryCaseStore


def test_inmemory_get_or_create_is_stable_and_saves() -> None:
    store = InMemoryCaseStore()

    async def scenario() -> None:
        first = await store.get_or_create("s1", language="uz", channel="web")
        again = await store.get_or_create("s1", language="ru", channel="telegram")
        assert again is first  # same session -> same case, original language kept
        assert again.language == "uz"

        first.domain = "imei"
        first.upsert(Fact(name="device_origin", value="imported", status=FactStatus.EXPLICIT))
        await store.save(first)
        loaded = await store.get("s1")
        assert loaded is not None and loaded.domain == "imei"
        assert loaded.has("device_origin")

        await store.reset("s1")
        assert await store.get("s1") is None

    asyncio.run(scenario())


def test_casestate_survives_json_roundtrip() -> None:
    # PostgresCaseStore persists via model_dump_json / model_validate_json.
    case = CaseState(
        case_id="c1", session_id="s1", domain="imei", active_tree="t", pending_node="n"
    )
    case.upsert(Fact(name="declaration_status", value="not_declared", status=FactStatus.EXPLICIT))
    case.turn_count = 3

    restored = CaseState.model_validate_json(case.model_dump_json())

    assert restored == case  # every field, including facts and provenance, preserved
    assert restored.facts["declaration_status"].status is FactStatus.EXPLICIT
