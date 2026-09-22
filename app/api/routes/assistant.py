"""Knowledge-base retrieval and grounded-answer endpoints.

``/assistant/retrieve`` returns grounded context, sources and a system prompt
without calling any LLM, so retrieval stays testable independently of the model.
``/assistant/answer`` composes the generation layer on top: it retrieves, then
asks the configured provider (mock / OpenAI / Ollama, per ``.env``) for a grounded
answer. When nothing is retrieved it escalates to a human without calling the LLM.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.domain.diagnostics import DecisionTree, DiagnosticNode, ResolutionCard
from app.domain.enums import Category, Language
from app.domain.schemas import LLMRequest
from app.providers.base import LLMProvider
from app.providers.errors import ProviderError
from app.services.audit_log import (
    OUTCOME_CLARIFY,
    OUTCOME_HANDOFF,
    OUTCOME_QUESTION,
    OUTCOME_RESOLVED,
    AuditEvent,
    AuditLog,
)
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.kb_retriever import (
    RetrievedChunk,
    build_system_prompt,
    get_retriever,
    taxonomy,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])

_DEFAULT_ANSWER_TOP_K = 5
_LANGUAGE_BY_CODE = {"uz": Language.UZ, "ru": Language.RU, "en": Language.EN}
_CATEGORY_BY_DOMAIN = {
    "imei": Category.IMEI,
    "mnp": Category.MNP,
    "aloqa_sifati": Category.NETWORK_QUALITY,
}


class RetrieveRequest(BaseModel):
    """One retrieval query with optional taxonomy filters."""

    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    domain: str | None = None
    case_type: str | None = None


class AnswerRequest(RetrieveRequest):
    """A retrieval query plus the language the answer should be written in."""

    language: str = Field(default="uz", pattern="^(uz|ru|en)$")


class RetrievedSource(BaseModel):
    """A single retrieved chunk's public metadata."""

    doc_id: str
    title: str
    source_type: str
    authority: int
    domain: str
    case_type: str
    score: float


class RetrieveResponse(BaseModel):
    """Grounded context returned without a generation step."""

    mode: str
    query: str
    sources: list[RetrievedSource]
    context: str
    system_prompt: str


class AnswerResponse(BaseModel):
    """A grounded answer (or a human-handoff signal) plus its sources."""

    mode: str
    query: str
    answer: str | None
    citations: list[str]
    sources: list[RetrievedSource]
    requires_human: bool
    reason: str | None
    model: str | None
    input_tokens: int
    output_tokens: int


def _to_source(result: RetrievedChunk) -> RetrievedSource:
    return RetrievedSource(
        doc_id=result.chunk.doc_id,
        title=result.chunk.title,
        source_type=result.chunk.source_type,
        authority=result.chunk.authority,
        domain=result.chunk.domain,
        case_type=result.chunk.case_type,
        score=result.score,
    )


@router.get("/health")
def assistant_health() -> dict[str, object]:
    """Report corpus size, per-layer counts and the retrieval mode."""
    return get_retriever().stats()


@router.get("/taxonomy")
def assistant_taxonomy() -> dict[str, object]:
    """Return category filters (domain / case_type / outcome) for the frontend."""
    return taxonomy()


@router.post("/retrieve", response_model=RetrieveResponse)
def assistant_retrieve(payload: RetrieveRequest) -> RetrieveResponse:
    """Return grounded context, sources and a system prompt. No LLM call."""
    retriever = get_retriever()
    results = retriever.retrieve(
        payload.query,
        payload.top_k,
        domain=payload.domain,
        case_type=payload.case_type,
    )
    context = "\n\n".join(result.chunk.text for result in results)
    return RetrieveResponse(
        mode=retriever.mode,
        query=payload.query,
        sources=[_to_source(result) for result in results],
        context=context,
        system_prompt=build_system_prompt(payload.query, results),
    )


@router.post("/answer", response_model=AnswerResponse)
async def assistant_answer(payload: AnswerRequest, request: Request) -> AnswerResponse:
    """Retrieve grounded context, then ask the configured provider to answer it.

    With no retrieved source the LLM is never called: the request escalates to a
    human, keeping the grounding-first guarantee.
    """
    retriever = get_retriever()
    results = retriever.retrieve(
        payload.query,
        payload.top_k or _DEFAULT_ANSWER_TOP_K,
        domain=payload.domain,
        case_type=payload.case_type,
    )
    sources = [_to_source(result) for result in results]

    if not results:
        return AnswerResponse(
            mode=retriever.mode,
            query=payload.query,
            answer=None,
            citations=[],
            sources=[],
            requires_human=True,
            reason="no_approved_source",
            model=None,
            input_tokens=0,
            output_tokens=0,
        )

    provider: LLMProvider = request.app.state.provider
    llm_request = LLMRequest(
        language=_LANGUAGE_BY_CODE[payload.language],
        question=payload.query,
        category=_CATEGORY_BY_DOMAIN.get(results[0].chunk.domain, Category.OTHER),
        source_ids=[result.chunk.doc_id for result in results],
        passages=[result.chunk.text for result in results],
    )

    try:
        result = await provider.generate(llm_request)
    except ProviderError:
        return AnswerResponse(
            mode=retriever.mode,
            query=payload.query,
            answer=None,
            citations=[],
            sources=sources,
            requires_human=True,
            reason="provider_unavailable",
            model=None,
            input_tokens=0,
            output_tokens=0,
        )

    return AnswerResponse(
        mode=retriever.mode,
        query=payload.query,
        answer=result.text,
        citations=result.citations,
        sources=sources,
        requires_human=False,
        reason=None,
        model=result.model_name,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# --- Conversational orchestration: free text -> tree -> questions -> answer ---

_LANGUAGE = {"uz": Language.UZ, "ru": Language.RU, "en": Language.EN}
_CATEGORY = {"imei": Category.IMEI, "mnp": Category.MNP}
_NO_TREE_REPLY = {
    "uz": "Kechirasiz, bu murojaatni IMEI yoki MNP bo'yicha aniqlay olmadim. "
    "Iltimos, muammoni biroz batafsilroq yozing yoki operatorga ulanishni so'rang.",
    "ru": "Извините, не удалось отнести обращение к IMEI или MNP. Опишите проблему "
    "подробнее или запросите оператора.",
    "en": "Sorry, I could not map this to IMEI or MNP. Please describe the problem in "
    "more detail or ask for an operator.",
}
_CLARIFY_REPLY = {
    "uz": "Tushunmadim. Iltimos, quyidagi variantlardan birini tanlang:",
    "ru": "Не понял. Пожалуйста, выберите один из вариантов ниже:",
    "en": "I did not understand. Please choose one of the options below:",
}


class ConverseRequest(BaseModel):
    """One turn of a diagnostic conversation."""

    message: str = Field(min_length=1, max_length=4000)
    tree_id: str | None = None
    node_id: str | None = None
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")


class ConverseOption(BaseModel):
    value: str
    label: str


class ConverseSource(BaseModel):
    doc_id: str
    title: str
    authority: int


class ConverseResponse(BaseModel):
    """Next question or the final grounded resolution."""

    tree_id: str | None
    node_id: str | None
    reply: str
    options: list[ConverseOption]
    done: bool
    card_id: str | None
    card_title: str | None = None
    official_url: str | None = None
    contact: str | None = None
    sources: list[ConverseSource]
    requires_human: bool
    reason: str | None


def _diagnostic_engine(request: Request) -> DiagnosticEngine:
    return cast(DiagnosticEngine, request.app.state.diagnostic_engine)


def _question(tree_id: str, node: DiagnosticNode, lang: str, prefix: str = "") -> ConverseResponse:
    reply = f"{prefix} {node.question.get(lang)}".strip() if prefix else node.question.get(lang)
    return ConverseResponse(
        tree_id=tree_id,
        node_id=node.id,
        reply=reply,
        options=[ConverseOption(value=o.value, label=o.label.get(lang)) for o in node.options],
        done=False,
        card_id=None,
        sources=[],
        requires_human=False,
        reason=None,
    )


def _handoff(reason: str, lang: str) -> ConverseResponse:
    return ConverseResponse(
        tree_id=None,
        node_id=None,
        reply=_NO_TREE_REPLY.get(lang, _NO_TREE_REPLY["uz"]),
        options=[],
        done=False,
        card_id=None,
        sources=[],
        requires_human=True,
        reason=reason,
    )


_ROUTE_REPLY = {
    "uz": "Muammoingizni aniqlashtiraylik. Quyidagilardan mos bo'lganini tanlang:",
    "ru": "Уточним вашу проблему. Выберите подходящий пункт:",
    "en": "Let's narrow it down. Please pick the closest option:",
}


def _routing_menu(engine: DiagnosticEngine, lang: str) -> ConverseResponse:
    """Offer the available trees as a menu when free text did not match one."""
    return ConverseResponse(
        tree_id=None,
        node_id=None,
        reply=_ROUTE_REPLY.get(lang, _ROUTE_REPLY["uz"]),
        options=[
            ConverseOption(value=tree.id, label=tree.title.get(lang))
            for tree in engine.trees()
        ],
        done=False,
        card_id=None,
        sources=[],
        requires_human=False,
        reason="clarify",
    )


def _card_context(card: ResolutionCard, lang: str) -> str:
    lines = [card.probable_cause.get(lang), "", "Qadamlar:"]
    lines += [f"{i}. {step.get(lang)}" for i, step in enumerate(card.steps, 1)]
    if card.documents:
        lines.append("Kerakli hujjatlar: " + ", ".join(d.get(lang) for d in card.documents))
    if card.where_to_apply:
        lines.append("Qayerga murojaat: " + card.where_to_apply.get(lang))
    if card.official_url:
        lines.append("Rasmiy manzil: " + card.official_url)
    if card.contact:
        lines.append("Kontakt: " + card.contact)
    if card.escalate_when:
        lines.append("Operatorga yo'naltirish: " + card.escalate_when.get(lang))
    return "\n".join(lines)


async def _resolve(
    tree: DecisionTree, card: ResolutionCard, message: str, lang: str, provider: LLMProvider
) -> ConverseResponse:
    retriever = get_retriever()
    facts = retriever.sources_by_doc_ids(card.kb_refs)
    card_context = _card_context(card, lang)
    passages = [card_context] + [fact.text for fact in facts]
    source_ids = [f"yechim-kartasi:{card.id}"] + [fact.doc_id for fact in facts]

    reply = card_context  # deterministic, grounded fallback
    try:
        result = await provider.generate(
            LLMRequest(
                language=_LANGUAGE[lang],
                question=message,
                category=_CATEGORY.get(tree.domain, Category.OTHER),
                source_ids=source_ids,
                passages=passages,
            )
        )
        reply = result.text
    except ProviderError:
        reply = card_context

    sources = [
        ConverseSource(
            doc_id=fact.doc_id,
            title=fact.title or fact.source_title,
            authority=fact.authority,
        )
        for fact in facts
    ]
    return ConverseResponse(
        tree_id=tree.id,
        node_id=None,
        reply=reply,
        options=[],
        done=True,
        card_id=card.id,
        card_title=card.title.get(lang),
        official_url=card.official_url,
        contact=card.contact,
        sources=sources,
        requires_human=False,
        reason=None,
    )


def _turn_outcome(response: ConverseResponse) -> str:
    if response.card_id:
        return OUTCOME_RESOLVED
    if response.requires_human:
        return OUTCOME_HANDOFF
    if response.reason == "clarify":
        return OUTCOME_CLARIFY
    return OUTCOME_QUESTION


def _category_of(tree_id: str | None) -> str | None:
    if not tree_id:
        return None
    if tree_id.startswith("imei"):
        return "imei"
    if tree_id.startswith("mnp"):
        return "mnp"
    return None


async def _run_diagnose(
    engine: DiagnosticEngine, provider: LLMProvider, payload: ConverseRequest, lang: str
) -> ConverseResponse:
    if payload.tree_id and payload.node_id:
        tree = engine.get_tree(payload.tree_id)
        node = engine.get_node(payload.tree_id, payload.node_id)
        if tree is None or node is None:
            return _handoff("unknown_state", lang)
        value = engine.map_answer(payload.tree_id, payload.node_id, payload.message)
        if value is None:
            return _question(payload.tree_id, node, lang, prefix=_CLARIFY_REPLY[lang])
        next_node, card = engine.answer(payload.tree_id, payload.node_id, value)
        if next_node is not None:
            return _question(payload.tree_id, next_node, lang)
        if card is not None:
            return await _resolve(tree, card, payload.message, lang, provider)
        return _handoff("invalid_answer", lang)

    # A menu selection sends the chosen tree id as the message; an explicit
    # tree_id (without a node) also starts that tree. Otherwise match free text.
    tree = engine.get_tree(payload.message.strip())
    if tree is None and payload.tree_id:
        tree = engine.get_tree(payload.tree_id)
    if tree is None:
        tree = engine.match_tree(payload.message)
    if tree is None:
        return _routing_menu(engine, lang)
    root = engine.get_node(tree.id, tree.root)
    assert root is not None  # integrity-checked at load
    return _question(tree.id, root, lang)


@router.post("/diagnose", response_model=ConverseResponse)
async def assistant_diagnose(payload: ConverseRequest, request: Request) -> ConverseResponse:
    """Drive one diagnostic turn: pick a tree, ask a question, or resolve.

    On the first turn the free-text problem is matched to a decision tree. On
    later turns the free-text answer is mapped to the current question's options;
    when a leaf is reached the resolution card is turned into a grounded answer by
    the configured provider (with a deterministic fallback). Every turn is audited.
    """
    engine = _diagnostic_engine(request)
    provider = cast(LLMProvider, request.app.state.provider)
    lang = payload.language

    response = await _run_diagnose(engine, provider, payload, lang)

    audit = cast(AuditLog, request.app.state.audit_log)
    await audit.record(
        AuditEvent(
            channel="web",
            language=lang,
            outcome=_turn_outcome(response),
            category=_category_of(response.tree_id),
            tree_id=response.tree_id,
            card_id=response.card_id,
            session_id=payload.tree_id,
        )
    )
    return response


@router.get("/metrics")
async def assistant_metrics(request: Request) -> dict[str, object]:
    """Return pilot KPIs (self-service resolution rate, handoff rate, counts)."""
    audit = cast(AuditLog, request.app.state.audit_log)
    return await audit.metrics()
