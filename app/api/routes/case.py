"""Case reasoning endpoints.

/assistant/understand builds the structured CaseState from a free-form story
(fact extraction). /assistant/converse is the full conversation brain: it greets
small talk, routes a topic, extracts facts, and walks the decision tree as a
fact guardrail - auto-skipping any question whose answer the user already gave and
asking only the next missing one, until an approved resolution card is reached.
It never invents facts.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.domain.case_state import CaseState, CaseStatus, Fact, FactStatus
from app.domain.diagnostics import DecisionTree, DiagnosticNode, ResolutionCard
from app.domain.enums import Category, Language
from app.domain.schemas import LLMRequest
from app.providers.base import LLMProvider
from app.providers.errors import ProviderError
from app.services.audit_log import (
    OUTCOME_ANSWER,
    OUTCOME_CLARIFY,
    OUTCOME_GREETING,
    OUTCOME_HANDOFF,
    OUTCOME_QUESTION,
    OUTCOME_RESOLVED,
    ROUTE_CASE,
    ROUTE_GREETING,
    ROUTE_RAG,
    AuditEvent,
    AuditLog,
)
from app.services.card_explainer import CardExplainer
from app.services.case_store import CaseStore
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.fact_extraction import (
    IMEI_FACT_FIELDS,
    MNP_FACT_FIELDS,
    FactExtractor,
    detect_domain,
)
from app.services.kb_retriever import get_retriever
from app.services.router import Route
from app.services.turn_analysis import TurnAnalyzer

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
    fields = {"imei": IMEI_FACT_FIELDS, "mnp": MNP_FACT_FIELDS}.get(case.domain or "")
    if fields is not None:
        case.unknown_facts = [name for name in fields if not case.has(name)]


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
_RAG_TOP_K = 5
# BM25 relevance floor: below this the top hit is too weak to answer from, so the
# assistant abstains instead of answering from irrelevant evidence. Calibrated on
# the corpus - on-topic queries score well above it, off-topic ones well below.
_RAG_MIN_SCORE = 4.0
_LANG_ENUM = {"uz": Language.UZ, "ru": Language.RU, "en": Language.EN}
_CATEGORY_BY_DOMAIN = {
    "imei": Category.IMEI,
    "mnp": Category.MNP,
    "aloqa_sifati": Category.NETWORK_QUALITY,
}
_NO_EVIDENCE_REPLY = {
    "uz": "Bu savolga tasdiqlangan manbadan aniq javob topa olmadim. "
    "Mutaxassisga yo'naltiraman.",
    "ru": "Не нашёл точного ответа в проверенных источниках. Передаю специалисту.",
    "en": "I couldn't find a confirmed source for this. I'll route you to a specialist.",
}


class ConverseCaseRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=100)
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")
    channel: str = Field(default="web", pattern="^(web|telegram)$")


class OptionOut(BaseModel):
    value: str
    label: str


class SourceOut(BaseModel):
    doc_id: str
    title: str


class ConverseCaseResponse(BaseModel):
    reply: str
    options: list[OptionOut]
    done: bool
    card_id: str | None
    domain: str | None
    known_facts: dict[str, str]
    unknown_facts: list[str]
    requires_human: bool
    sources: list[SourceOut] = []


async def _audit(
    audit: AuditLog,
    case: CaseState,
    outcome: str,
    route: str,
    *,
    card_id: str | None = None,
    tree_id: str | None = None,
) -> None:
    """Record one converse turn for the KPI metrics."""
    await audit.record(
        AuditEvent(
            channel=case.channel,
            language=case.language,
            outcome=outcome,
            category=case.domain,
            tree_id=tree_id,
            card_id=card_id,
            session_id=case.session_id,
            route=route,
        )
    )


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
    sources: list[SourceOut] | None = None,
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
        sources=sources or [],
    )


def _menu(
    case: CaseState, trees: list[DecisionTree], intro: str, lang: str
) -> ConverseCaseResponse:
    options = [OptionOut(value=tree.id, label=tree.title.get(lang)) for tree in trees]
    return _resp(case, intro, options=options)


_STEPS_HEADER = {"uz": "Qadamlar:", "ru": "Шаги:", "en": "Steps:"}
_WHERE_LABEL = {"uz": "Qayerga", "ru": "Куда обратиться", "en": "Where"}


async def _card_reply(
    explainer: CardExplainer, card: ResolutionCard, case: CaseState, lang: str
) -> str:
    """Compose the resolution: an LLM-explained cause, then the exact approved
    steps, link and contact (never touched by the LLM)."""
    cause = await explainer.explain(card.probable_cause.get(lang), case, lang)
    lines = [cause, "", _STEPS_HEADER.get(lang, _STEPS_HEADER["uz"])]
    lines += [f"{index}. {step.get(lang)}" for index, step in enumerate(card.steps, 1)]
    if card.where_to_apply:
        where_label = _WHERE_LABEL.get(lang, _WHERE_LABEL["uz"])
        lines.append(f"{where_label}: {card.where_to_apply.get(lang)}")
    if card.official_url:
        lines.append("🔗 " + card.official_url)
    if card.contact:
        lines.append("📞 " + card.contact)
    return "\n".join(lines)


def _apply_option(
    engine: DiagnosticEngine, case: CaseState, value: str
) -> ResolutionCard | None:
    """Apply the chosen option on the pending node: set its fact, advance/resolve."""
    node = engine.get_node(case.active_tree or "", case.pending_node or "")
    if node is None:
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


def _has_strong_evidence(results: list[Any], min_score: float) -> bool:
    """True when the top retrieved passage clears the relevance floor."""
    return bool(results) and results[0].score >= min_score


async def _rag_answer(
    provider: LLMProvider, case: CaseState, message: str, lang: str
) -> ConverseCaseResponse:
    """Answer an informational question strictly from approved KB evidence.

    Retrieves the top approved passages and lets the provider answer only from
    them, returning the sources. With no evidence (or a provider failure) it
    escalates instead of inventing an answer - grounding-first, like /answer.
    """
    retriever = get_retriever()
    results = retriever.retrieve(message, _RAG_TOP_K, domain=case.domain)
    fallback = _NO_EVIDENCE_REPLY.get(lang, _NO_EVIDENCE_REPLY["uz"])
    # Abstain when there is no evidence or the best hit is too weak to trust.
    if not _has_strong_evidence(results, _RAG_MIN_SCORE):
        return _resp(case, fallback, done=True, requires_human=True)
    llm_request = LLMRequest(
        language=_LANG_ENUM.get(lang, Language.UZ),
        question=message,
        category=_CATEGORY_BY_DOMAIN.get(results[0].chunk.domain, Category.OTHER),
        source_ids=[r.chunk.doc_id for r in results],
        passages=[r.chunk.text for r in results],
    )
    try:
        result = await provider.generate(llm_request)
    except ProviderError:
        return _resp(case, fallback, done=True, requires_human=True)
    sources = [SourceOut(doc_id=r.chunk.doc_id, title=r.chunk.title) for r in results]
    return _resp(case, result.text, done=True, sources=sources)


@router.post("/converse", response_model=ConverseCaseResponse)
async def assistant_converse(
    payload: ConverseCaseRequest, request: Request
) -> ConverseCaseResponse:
    """One conversation turn: greet, route, extract facts, ask only what's missing."""
    store = cast(CaseStore, request.app.state.case_store)
    analyzer = cast(TurnAnalyzer, request.app.state.turn_analyzer)
    engine = cast(DiagnosticEngine, request.app.state.diagnostic_engine)
    provider = cast(LLMProvider, request.app.state.provider)
    explainer = cast(CardExplainer, request.app.state.card_explainer)
    audit = cast(AuditLog, request.app.state.audit_log)

    case = store.get_or_create(
        payload.session_id, language=payload.language, channel=payload.channel
    )
    case.turn_count += 1
    lang = payload.language

    # A previously closed case starts fresh so old facts don't auto-complete a new one.
    if case.status in (CaseStatus.RESOLVED, CaseStatus.HANDOFF):
        _start_fresh_case(case)

    # 1) Understand the message every turn (route + facts in one LLM call), so a
    #    new story is never ignored.
    analysis = await analyzer.analyze(payload.message, case, turn_id=case.turn_count)
    for fact in analysis.facts:
        case.upsert(fact)
    if case.domain is None:
        case.domain = detect_domain(payload.message)
    _refresh_unknowns(case)

    # 2) If a question is open and this message answers it, take that answer.
    answered = False
    if case.active_tree and case.pending_node:
        value = engine.map_answer(case.active_tree, case.pending_node, payload.message)
        if value is not None:
            resolved = _apply_option(engine, case, value)
            if resolved is not None:
                _refresh_unknowns(case)
                store.save(case)
                await _audit(audit, case, OUTCOME_RESOLVED, ROUTE_CASE, card_id=resolved.id)
                card_text = await _card_reply(explainer, resolved, case, lang)
                return _resp(case, card_text, done=True, card_id=resolved.id)
            answered = True

    # 3) Not an answer to an open question: pick the lane for this message.
    if not answered:
        matched, route_domain = engine.route(payload.message)
        chosen = (
            engine.get_tree(payload.message.strip())
            or matched
            or engine.tree_from_facts(case.known_facts(), domain=case.domain)
        )

        # 3a) A curated resolution card the facts already complete beats everything:
        #     an approved answer (e.g. mnp-docs, imei-customs) wins over free RAG.
        if chosen is not None:
            kind, obj = engine.advance(chosen.id, chosen.root, case.known_facts())
            if kind == "resolve" and isinstance(obj, ResolutionCard):
                case.active_tree = None
                case.pending_node = None
                case.resolution_card_id = obj.id
                case.status = CaseStatus.RESOLVED
                if case.domain is None:
                    case.domain = chosen.domain
                store.save(case)
                await _audit(
                    audit, case, OUTCOME_RESOLVED, ROUTE_CASE, card_id=obj.id, tree_id=chosen.id
                )
                card_text = await _card_reply(explainer, obj, case, lang)
                return _resp(case, card_text, done=True, card_id=obj.id)

        # 3b) No ready card: the router's decision (from step 1) picks the lane.
        route = analysis.route
        if route is Route.GREETING and case.active_tree is None:
            store.save(case)
            await _audit(audit, case, OUTCOME_GREETING, ROUTE_GREETING)
            return _resp(case, _GREETING.get(lang, _GREETING["uz"]))
        if route is Route.RAG:
            reply = await _rag_answer(provider, case, payload.message, lang)
            outcome = OUTCOME_HANDOFF if reply.requires_human else OUTCOME_ANSWER
            await _audit(audit, case, outcome, ROUTE_RAG)  # record before the reset
            # A standalone question leaves no residue; a question mid-diagnosis
            # keeps the open case so the next message can still answer it.
            if case.active_tree is None:
                _start_fresh_case(case)
            store.save(case)
            return reply

        # 3c) CASE: enter the chosen tree, or clarify with a menu when none fits.
        if chosen is None and case.active_tree is None:
            menu_domain = route_domain or case.domain
            if menu_domain is not None and engine.trees_for_domain(menu_domain):
                by_lang = _DOMAIN_INTRO.get(lang, _DOMAIN_INTRO["uz"])
                intro = by_lang.get(menu_domain) or _ROUTE_INTRO.get(lang, _ROUTE_INTRO["uz"])
                store.save(case)
                await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_CASE)
                return _menu(case, engine.trees_for_domain(menu_domain), intro, lang)
            store.save(case)
            await _audit(audit, case, OUTCOME_CLARIFY, ROUTE_CASE)
            return _menu(case, engine.trees(), _ROUTE_INTRO.get(lang, _ROUTE_INTRO["uz"]), lang)
        if chosen is not None and chosen.id != case.active_tree:
            case.active_tree = chosen.id
            case.pending_node = chosen.root
            if case.domain is None:
                case.domain = chosen.domain
            _refresh_unknowns(case)

    # 4) Walk from the current node, skipping questions the facts already answer.
    active_tree = case.active_tree
    kind, obj = engine.advance(case.active_tree or "", case.pending_node or "", case.known_facts())
    if kind == "resolve" and isinstance(obj, ResolutionCard):
        case.resolution_card_id = obj.id
        case.status = CaseStatus.RESOLVED
        case.active_tree = None
        case.pending_node = None
        store.save(case)
        await _audit(audit, case, OUTCOME_RESOLVED, ROUTE_CASE, card_id=obj.id, tree_id=active_tree)
        card_text = await _card_reply(explainer, obj, case, lang)
        return _resp(case, card_text, done=True, card_id=obj.id)
    if kind == "ask" and isinstance(obj, DiagnosticNode):
        case.pending_node = obj.id
        case.status = CaseStatus.DIAGNOSING
        store.save(case)
        await _audit(audit, case, OUTCOME_QUESTION, ROUTE_CASE, tree_id=active_tree)
        options = [OptionOut(value=o.value, label=o.label.get(lang)) for o in obj.options]
        return _resp(case, obj.question.get(lang), options=options)

    case.status = CaseStatus.HANDOFF
    case.active_tree = None
    case.pending_node = None
    store.save(case)
    await _audit(audit, case, OUTCOME_HANDOFF, ROUTE_CASE, tree_id=active_tree)
    return _resp(case, _HANDOFF_REPLY.get(lang, _HANDOFF_REPLY["uz"]), requires_human=True)
