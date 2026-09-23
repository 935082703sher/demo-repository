"""Case reasoning endpoints.

/assistant/understand builds the structured CaseState from a free-form story
(fact extraction). /assistant/converse is the full conversation brain: it greets
small talk, routes a topic, extracts facts, and walks the decision tree as a
fact guardrail - auto-skipping any question whose answer the user already gave and
asking only the next missing one, until an approved resolution card is reached.
It never invents facts.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus
from app.domain.diagnostics import DecisionTree, DiagnosticNode, ResolutionCard
from app.services.case_store import CaseStore
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.fact_extraction import IMEI_FACT_FIELDS, FactExtractor, detect_domain

router = APIRouter(prefix="/assistant", tags=["case"])


# --- /assistant/understand: story -> facts (no conversation control) -----------


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


def _refresh_unknowns(case: CaseState) -> None:
    if case.domain == "imei":
        case.unknown_facts = [name for name in IMEI_FACT_FIELDS if not case.has(name)]


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
    _refresh_unknowns(case)
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


# --- /assistant/converse: the full conversation brain --------------------------

_SMALLTALK_TERMS = (
    "salom", "assalom", "alaykum", "hello", "hi", "hey", "hayrli", "qandaysan",
    "qalaysan", "yaxshimisiz", "rahmat", "tashakkur", "xayr", "how are you",
    "thanks", "thank you", "privet", "zdravstvuy", "spasibo", "poka", "kak dela",
)
_GREETING = {
    "uz": "Assalomu alaykum! Men IMEI va MNP bo'yicha yordam beraman. Muammoingizni "
    "o'z so'zlaringiz bilan yozing — masalan «telefonim chetdan, ro'yxatdan o'tmayapti» "
    "yoki «raqamni boshqa operatorga ko'chirmoqchiman».",
    "ru": "Здравствуйте! Я помогаю по IMEI и MNP. Опишите проблему своими словами — "
    "например «телефон из-за границы, не регистрируется» или «хочу перенести номер».",
    "en": "Hello! I help with IMEI and MNP. Describe your problem in your own words.",
}
_ROUTE_INTRO = {
    "uz": "Muammoingizni aniqlashtiraylik. Quyidagilardan mos bo'lganini tanlang:",
    "ru": "Уточним вашу проблему. Выберите подходящий пункт:",
    "en": "Let's narrow it down. Please pick the closest option:",
}
_DOMAIN_INTRO = {
    "uz": {"imei": "IMEI bo'yicha aynan qanday yordam kerak?",
           "mnp": "MNP bo'yicha aynan qanday yordam kerak?"},
    "ru": {"imei": "Что именно нужно по IMEI?", "mnp": "Что именно нужно по MNP?"},
}
_HANDOFF_REPLY = {
    "uz": "Bu masalani mutaxassisga yo'naltiraman.",
    "ru": "Передаю вопрос специалисту.",
    "en": "I'll route this to a specialist.",
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


def _is_smalltalk(message: str) -> bool:
    norm = message.lower().replace("'", "").replace("ʻ", "").replace("`", "")
    return any(term in norm for term in _SMALLTALK_TERMS)


def _start_fresh_case(case: CaseState) -> None:
    """Clear the diagnostic slate for a new problem, keeping the session identity.

    Once a case is resolved or handed off, the next message is a new problem: its
    facts must not be auto-completed by the previous case's facts. Session id,
    turn count, language and channel are preserved.
    """
    case.facts.clear()
    case.unknown_facts = []
    case.candidate_issues = []
    case.domain = None
    case.diagnosis = None
    case.diagnosis_confidence = None
    case.resolution_card_id = None
    case.active_tree = None
    case.pending_node = None
    case.status = CaseStatus.UNDERSTANDING


def _resp(
    case: CaseState,
    reply: str,
    *,
    options: list[OptionOut] | None = None,
    done: bool = False,
    card_id: str | None = None,
    requires_human: bool = False,
) -> ConverseCaseResponse:
    return ConverseCaseResponse(
        reply=reply,
        options=options or [],
        done=done,
        card_id=card_id,
        domain=case.domain,
        known_facts=case.known_facts(),
        unknown_facts=case.unknown_facts,
        requires_human=requires_human,
    )


def _menu(
    case: CaseState, trees: list[DecisionTree], intro: str, lang: str
) -> ConverseCaseResponse:
    options = [OptionOut(value=tree.id, label=tree.title.get(lang)) for tree in trees]
    return _resp(case, intro, options=options)


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


def _apply_pending_answer(
    engine: DiagnosticEngine, case: CaseState, message: str
) -> ResolutionCard | None:
    """Apply a reply to the pending question: set its fact and advance/resolve."""
    if not (case.active_tree and case.pending_node):
        return None
    node = engine.get_node(case.active_tree, case.pending_node)
    if node is None:
        return None
    value = engine.map_answer(case.active_tree, case.pending_node, message)
    if value is None:
        return None
    option = next((o for o in node.options if o.value == value), None)
    if option is None:
        return None
    if node.fact and option.fact_value:
        case.upsert(
            Fact(
                name=node.fact,
                value=option.fact_value,
                status=FactStatus.EXPLICIT,
                source="answer",
                turn_id=case.turn_count,
            )
        )
    if option.card is not None:
        case.resolution_card_id = option.card
        case.status = CaseStatus.RESOLVED
        case.active_tree = None
        case.pending_node = None
        return engine.get_card(option.card)
    if option.next_node is not None:
        case.pending_node = option.next_node
    return None


@router.post("/converse", response_model=ConverseCaseResponse)
async def assistant_converse(
    payload: ConverseCaseRequest, request: Request
) -> ConverseCaseResponse:
    """One conversation turn: greet, route, extract facts, ask only what's missing."""
    store = cast(CaseStore, request.app.state.case_store)
    extractor = cast(FactExtractor, request.app.state.fact_extractor)
    engine = cast(DiagnosticEngine, request.app.state.diagnostic_engine)

    case = store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1
    lang = payload.language

    # A previously closed case starts fresh so old facts don't auto-complete a new one.
    if case.status in (CaseStatus.RESOLVED, CaseStatus.HANDOFF):
        _start_fresh_case(case)

    # A) A reply to the pending question becomes a fact and advances / resolves.
    resolved = _apply_pending_answer(engine, case, payload.message)
    if resolved is not None:
        _refresh_unknowns(case)
        store.save(case)
        return _resp(case, _card_reply(resolved, lang), done=True, card_id=resolved.id)

    # B) Understand the (possibly rich) message.
    for fact in await extractor.extract(payload.message, case, turn_id=case.turn_count):
        case.upsert(fact)
    if case.domain is None:
        case.domain = detect_domain(payload.message)
    _refresh_unknowns(case)

    # C) No active tree yet: menu selection, routed tree, domain menu, greeting or menu.
    if case.active_tree is None:
        chosen = engine.get_tree(payload.message.strip())
        if chosen is None:
            matched, domain = engine.route(payload.message)
            # No specific tree, but if we know the domain (from routing tie or fact
            # extraction) offer that domain's topics instead of the whole menu.
            menu_domain = domain or case.domain
            if matched is not None:
                chosen = matched
            elif menu_domain is not None and engine.trees_for_domain(menu_domain):
                by_lang = _DOMAIN_INTRO.get(lang, _DOMAIN_INTRO["uz"])
                intro = by_lang.get(menu_domain) or _ROUTE_INTRO.get(lang, _ROUTE_INTRO["uz"])
                store.save(case)
                return _menu(case, engine.trees_for_domain(menu_domain), intro, lang)
            elif _is_smalltalk(payload.message):
                store.save(case)
                return _resp(case, _GREETING.get(lang, _GREETING["uz"]))
            else:
                store.save(case)
                return _menu(case, engine.trees(), _ROUTE_INTRO.get(lang, _ROUTE_INTRO["uz"]), lang)
        case.active_tree = chosen.id
        case.pending_node = chosen.root
        if case.domain is None:
            case.domain = chosen.domain
        _refresh_unknowns(case)

    # D) Walk from the current node, skipping questions the facts already answer.
    kind, obj = engine.advance(case.active_tree, case.pending_node or "", case.known_facts())
    if kind == "resolve" and isinstance(obj, ResolutionCard):
        case.resolution_card_id = obj.id
        case.status = CaseStatus.RESOLVED
        case.active_tree = None
        case.pending_node = None
        store.save(case)
        return _resp(case, _card_reply(obj, lang), done=True, card_id=obj.id)
    if kind == "ask" and isinstance(obj, DiagnosticNode):
        case.pending_node = obj.id
        case.status = CaseStatus.DIAGNOSING
        store.save(case)
        options = [OptionOut(value=o.value, label=o.label.get(lang)) for o in obj.options]
        return _resp(case, obj.question.get(lang), options=options)

    case.status = CaseStatus.HANDOFF
    case.active_tree = None
    case.pending_node = None
    store.save(case)
    return _resp(case, _HANDOFF_REPLY.get(lang, _HANDOFF_REPLY["uz"]), requires_human=True)
