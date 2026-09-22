"""Knowledge-base retrieval and grounded-answer endpoints.

``/assistant/retrieve`` returns grounded context, sources and a system prompt
without calling any LLM, so retrieval stays testable independently of the model.
``/assistant/answer`` composes the generation layer on top: it retrieves, then
asks the configured provider (mock / OpenAI / Ollama, per ``.env``) for a grounded
answer. When nothing is retrieved it escalates to a human without calling the LLM.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.domain.enums import Category, Language
from app.domain.schemas import LLMRequest
from app.providers.base import LLMProvider
from app.providers.errors import ProviderError
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
