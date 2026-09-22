"""Diagnostic decision-tree endpoints (the assistant's diagnostic logic).

Stateless step API: the client starts with a free-text problem (or an explicit
tree), gets one question at a time, and sends back the chosen answer until a
resolution card is returned. A card carries the approved steps plus the linked
knowledge-base facts (kb_sources) and anonymized practice examples (case_guidance).
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.domain.diagnostics import DiagnosticNode, ResolutionCard
from app.services.diagnostic_engine import DiagnosticEngine
from app.services.kb_retriever import get_retriever

router = APIRouter(prefix="/assistant/diagnostics", tags=["diagnostics"])


class StepRequest(BaseModel):
    """Start (query) or continue (tree_id + node_id + answer) a diagnosis."""

    query: str | None = Field(default=None, max_length=4000)
    tree_id: str | None = None
    node_id: str | None = None
    answer: str | None = None
    language: str = Field(default="uz", pattern="^(uz|ru|en)$")


class OptionOut(BaseModel):
    value: str
    label: str


class NodeOut(BaseModel):
    tree_id: str
    node_id: str
    question: str
    options: list[OptionOut]


class SourceOut(BaseModel):
    doc_id: str
    title: str
    source_type: str
    authority: int


class GuidanceOut(BaseModel):
    doc_id: str
    excerpt: str


class CardOut(BaseModel):
    id: str
    title: str
    probable_cause: str
    steps: list[str]
    documents: list[str]
    where_to_apply: str | None
    official_url: str | None
    contact: str | None
    escalate_when: str | None
    kb_sources: list[SourceOut]
    case_guidance: list[GuidanceOut]


class TreeOut(BaseModel):
    id: str
    domain: str
    case_type: str
    title: str


class StepResponse(BaseModel):
    tree_id: str | None
    node: NodeOut | None
    card: CardOut | None
    done: bool
    requires_human: bool
    message: str | None


def _engine(request: Request) -> DiagnosticEngine:
    return cast(DiagnosticEngine, request.app.state.diagnostic_engine)


def _node_out(tree_id: str, node: DiagnosticNode, lang: str) -> NodeOut:
    return NodeOut(
        tree_id=tree_id,
        node_id=node.id,
        question=node.question.get(lang),
        options=[OptionOut(value=o.value, label=o.label.get(lang)) for o in node.options],
    )


def _card_out(card: ResolutionCard, case_type: str, lang: str) -> CardOut:
    retriever = get_retriever()
    sources = [
        SourceOut(
            doc_id=chunk.doc_id,
            title=chunk.title or chunk.source_title,
            source_type=chunk.source_type,
            authority=chunk.authority,
        )
        for chunk in retriever.sources_by_doc_ids(card.kb_refs)
    ]
    guidance = [
        GuidanceOut(doc_id=chunk.doc_id, excerpt=chunk.text[:280])
        for chunk in retriever.case_guidance(case_type)
    ]
    return CardOut(
        id=card.id,
        title=card.title.get(lang),
        probable_cause=card.probable_cause.get(lang),
        steps=[step.get(lang) for step in card.steps],
        documents=[doc.get(lang) for doc in card.documents],
        where_to_apply=card.where_to_apply.get(lang) if card.where_to_apply else None,
        official_url=card.official_url,
        contact=card.contact,
        escalate_when=card.escalate_when.get(lang) if card.escalate_when else None,
        kb_sources=sources,
        case_guidance=guidance,
    )


@router.get("/trees")
def list_trees(request: Request, language: str = "uz") -> list[TreeOut]:
    """List the available diagnostic trees for frontend selection."""
    return [
        TreeOut(id=t.id, domain=t.domain, case_type=t.case_type, title=t.title.get(language))
        for t in _engine(request).trees()
    ]


@router.post("/step", response_model=StepResponse)
def diagnostic_step(payload: StepRequest, request: Request) -> StepResponse:
    """Return the next question or a resolution card. No LLM call."""
    engine = _engine(request)
    lang = payload.language

    # Continue an in-progress diagnosis.
    if payload.tree_id and payload.node_id and payload.answer is not None:
        tree = engine.get_tree(payload.tree_id)
        next_node, card = engine.answer(payload.tree_id, payload.node_id, payload.answer)
        if next_node is not None:
            return StepResponse(
                tree_id=payload.tree_id, node=_node_out(payload.tree_id, next_node, lang),
                card=None, done=False, requires_human=False, message=None,
            )
        if card is not None and tree is not None:
            return StepResponse(
                tree_id=payload.tree_id, node=None,
                card=_card_out(card, tree.case_type, lang),
                done=True, requires_human=False, message=None,
            )
        return StepResponse(
            tree_id=payload.tree_id, node=None, card=None, done=False,
            requires_human=True, message="invalid_answer",
        )

    # Start a new diagnosis: match the problem to a tree, or use an explicit tree.
    tree = engine.get_tree(payload.tree_id) if payload.tree_id else None
    if tree is None and payload.query:
        tree = engine.match_tree(payload.query)
    if tree is None:
        return StepResponse(
            tree_id=None, node=None, card=None, done=False,
            requires_human=True, message="no_matching_tree",
        )
    root = engine.get_node(tree.id, tree.root)
    assert root is not None  # integrity-checked at load
    return StepResponse(
        tree_id=tree.id, node=_node_out(tree.id, root, lang),
        card=None, done=False, requires_human=False, message=None,
    )
