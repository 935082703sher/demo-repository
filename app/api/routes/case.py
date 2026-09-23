"""Case understanding endpoint (phase 1): free-form story -> structured facts.

This does not drive the conversation yet; it builds and persists the CaseState so
later phases (missing-fact reasoning, next-best-question, diagnosis) can use it.
It never invents facts - anything not clearly stated stays UNKNOWN.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.services.case_store import CaseStore
from app.services.fact_extraction import IMEI_FACT_FIELDS, FactExtractor, detect_domain

router = APIRouter(prefix="/assistant", tags=["case"])


class UnderstandRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=100)
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")
    channel: str = Field(default="web", pattern="^(web|telegram)$")


class FactOut(BaseModel):
    name: str
    value: str | None
    status: str
    confidence: float
    source: str


class UnderstandResponse(BaseModel):
    case_id: str
    session_id: str
    domain: str | None
    status: str
    turn_count: int
    known_facts: dict[str, str]
    unknown_facts: list[str]
    facts: list[FactOut]


@router.post("/understand", response_model=UnderstandResponse)
def assistant_understand(payload: UnderstandRequest, request: Request) -> UnderstandResponse:
    """Update the session's case with facts extracted from this message."""
    store = cast(CaseStore, request.app.state.case_store)
    extractor = cast(FactExtractor, request.app.state.fact_extractor)

    case = store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1
    if case.domain is None:
        case.domain = detect_domain(payload.message)

    for fact in extractor.extract(payload.message, case, turn_id=case.turn_count):
        case.upsert(fact)

    if case.domain == "imei":
        case.unknown_facts = [name for name in IMEI_FACT_FIELDS if not case.has(name)]

    store.save(case)

    return UnderstandResponse(
        case_id=case.case_id,
        session_id=case.session_id,
        domain=case.domain,
        status=case.status.value,
        turn_count=case.turn_count,
        known_facts=case.known_facts(),
        unknown_facts=case.unknown_facts,
        facts=[
            FactOut(
                name=fact.name,
                value=fact.value,
                status=fact.status.value,
                confidence=fact.confidence,
                source=fact.source,
            )
            for fact in case.facts.values()
        ],
    )
