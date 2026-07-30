"""Chat endpoint."""

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.domain.enums import ResponseType
from app.domain.schemas import ChatRequest, ChatResponse
from app.services.assistant import AssistantService

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse | JSONResponse:
    """Validate and process one controlled assistant message."""
    assistant = cast(AssistantService, request.app.state.assistant)
    response = await assistant.chat(payload, request.state.request_id)
    if response.response_type is ResponseType.RATE_LIMITED:
        retry_after = response.retry_after_seconds or 1
        return JSONResponse(
            status_code=429,
            content=response.model_dump(mode="json"),
            headers={"Retry-After": str(retry_after)},
        )
    return response
