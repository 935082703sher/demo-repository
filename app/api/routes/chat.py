"""Chat endpoint."""

from typing import cast

from fastapi import APIRouter, Request

from app.domain.schemas import ChatRequest, ChatResponse
from app.services.assistant import AssistantService

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Validate and process one controlled assistant message."""
    assistant = cast(AssistantService, request.app.state.assistant)
    return await assistant.chat(payload, request.state.request_id)
