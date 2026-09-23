"""Case understanding endpoint (phase 1): free-form story -> structured facts.

This does not drive the conversation yet; it builds and persists the CaseState so
later phases (missing-fact reasoning, next-best-question, diagnosis) can use it.
It never invents facts - anything not clearly stated stays UNKNOWN.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus
from app.domain.diagnostics import DiagnosticNode, ResolutionCard
from app.services.case_store import CaseStore
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.fact_extraction import IMEI_FACT_FIELDS, FactExtractor, detect_domain

router = APIRouter(prefix="/assistant", tags=["case"])

# Phase 1 wires the IMEI registration tree to the fact schema.
_IMEI_TREE = "imei-royxatdan_otkazish"


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
async def assistant_understand(payload: UnderstandRequest, request: Request) -> UnderstandResponse:
    """Update the session's case with facts extracted from this message."""
    store = cast(CaseStore, request.app.state.case_store)
    extractor = cast(FactExtractor, request.app.state.fact_extractor)

    case = store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1
    if case.domain is None:
        case.domain = detect_domain(payload.message)

    for fact in await extractor.extract(payload.message, case, turn_id=case.turn_count):
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


# --- Case-reasoning conversation (phase 2, IMEI): facts drive the tree ---------

_NEED_TOPIC = {
    "uz": "Muammoingizni biroz aniqroq yozing — IMEI (qurilma ro'yxati) yoki MNP "
    "(raqam ko'chirish) bo'yichami?",
    "ru": "Опишите проблему точнее — это по IMEI (регистрация устройства) или MNP "
    "(перенос номера)?",
    "en": "Please describe the problem a bit more — is it about IMEI or MNP?",
}


class ConverseCaseRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=100)
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")
    channel: str = Field(default="web", pattern="^(web|telegram)$")


class OptionOut(BaseModel):
    value: str
    label: str


class ConverseCaseResponse(BaseModel):
    reply: str
    options: list[OptionOut]
    done: bool
    card_id: str | None
    domain: str | None
    known_facts: dict[str, str]
    unknown_facts: list[str]
    requires_human: bool


def _question_reply(node: DiagnosticNode, lang: str) -> tuple[str, list[OptionOut]]:
    options = [OptionOut(value=o.value, label=o.label.get(lang)) for o in node.options]
    return node.question.get(lang), options


def _card_reply(card: ResolutionCard, lang: str) -> str:
    lines = [card.probable_cause.get(lang), "", "Qadamlar:"]
    lines += [f"{index}. {step.get(lang)}" for index, step in enumerate(card.steps, 1)]
    if card.where_to_apply:
        lines.append("Qayerga: " + card.where_to_apply.get(lang))
    if card.official_url:
        lines.append("🔗 " + card.official_url)
    if card.contact:
        lines.append("📞 " + card.contact)
    return "\n".join(lines)


def _answer_pending(engine: DiagnosticEngine, case: CaseState, message: str) -> None:
    """Map a reply to the pending question into a fact, so the walk advances."""
    if not (case.active_tree and case.pending_node):
        return
    value = engine.map_answer(case.active_tree, case.pending_node, message)
    node = engine.get_node(case.active_tree, case.pending_node)
    if value is None or node is None or node.fact is None:
        return
    option = next((o for o in node.options if o.value == value), None)
    if option is not None and option.fact_value is not None:
        case.upsert(
            Fact(
                name=node.fact,
                value=option.fact_value,
                status=FactStatus.EXPLICIT,
                source="answer",
                turn_id=case.turn_count,
            )
        )


@router.post("/converse", response_model=ConverseCaseResponse)
async def assistant_converse(
    payload: ConverseCaseRequest, request: Request
) -> ConverseCaseResponse:
    """Case-reasoning turn: extract facts, then ask only the missing critical one."""
    store = cast(CaseStore, request.app.state.case_store)
    extractor = cast(FactExtractor, request.app.state.fact_extractor)
    engine = cast(DiagnosticEngine, request.app.state.diagnostic_engine)

    case = store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1

    # 1) A short reply to the pending question becomes a fact.
    _answer_pending(engine, case, payload.message)
    # 2) Understand the (possibly rich) message.
    for fact in await extractor.extract(payload.message, case, turn_id=case.turn_count):
        case.upsert(fact)
    if case.domain is None:
        case.domain = detect_domain(payload.message)
    if case.domain == "imei":
        case.unknown_facts = [name for name in IMEI_FACT_FIELDS if not case.has(name)]

    lang = payload.language

    if case.domain != "imei":  # phase 2 covers IMEI; other domains ask to narrow down
        store.save(case)
        return ConverseCaseResponse(
            reply=_NEED_TOPIC.get(lang, _NEED_TOPIC["uz"]),
            options=[],
            done=False,
            card_id=None,
            domain=case.domain,
            known_facts=case.known_facts(),
            unknown_facts=case.unknown_facts,
            requires_human=False,
        )

    kind, obj = engine.walk(_IMEI_TREE, case.known_facts())
    if kind == "resolve" and isinstance(obj, ResolutionCard):
        case.status = CaseStatus.RESOLVED
        case.resolution_card_id = obj.id
        case.pending_node = None
        store.save(case)
        return ConverseCaseResponse(
            reply=_card_reply(obj, lang), options=[], done=True, card_id=obj.id,
            domain=case.domain, known_facts=case.known_facts(),
            unknown_facts=case.unknown_facts, requires_human=False,
        )
    if kind == "ask" and isinstance(obj, DiagnosticNode):
        case.status = CaseStatus.DIAGNOSING
        case.active_tree = _IMEI_TREE
        case.pending_node = obj.id
        store.save(case)
        reply, options = _question_reply(obj, lang)
        return ConverseCaseResponse(
            reply=reply, options=options, done=False, card_id=None,
            domain=case.domain, known_facts=case.known_facts(),
            unknown_facts=case.unknown_facts, requires_human=False,
        )

    store.save(case)  # stuck: hand off
    case.status = CaseStatus.HANDOFF
    return ConverseCaseResponse(
        reply="Bu masalani mutaxassisga yo'naltiraman.", options=[], done=False,
        card_id=None, domain=case.domain, known_facts=case.known_facts(),
        unknown_facts=case.unknown_facts, requires_human=True,
    )
