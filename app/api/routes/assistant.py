"""Knowledge-base retrieval endpoints.

These endpoints expose the BM25 retriever without calling any LLM: given a
question they return the grounded context, its sources and a ready-to-use system
prompt. The generation layer is composed on top, so retrieval stays testable
independently of the model.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.kb_retriever import build_system_prompt, get_retriever, taxonomy

router = APIRouter(prefix="/assistant", tags=["assistant"])


class RetrieveRequest(BaseModel):
    """One retrieval query with optional taxonomy filters."""

    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    domain: str | None = None
    case_type: str | None = None


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
    sources = [
        RetrievedSource(
            doc_id=result.chunk.doc_id,
            title=result.chunk.title,
            source_type=result.chunk.source_type,
            authority=result.chunk.authority,
            domain=result.chunk.domain,
            case_type=result.chunk.case_type,
            score=result.score,
        )
        for result in results
    ]
    context = "\n\n".join(result.chunk.text for result in results)
    return RetrieveResponse(
        mode=retriever.mode,
        query=payload.query,
        sources=sources,
        context=context,
        system_prompt=build_system_prompt(payload.query, results),
    )
