"""Minimal static test page for manually demonstrating the assistant."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["demo-ui"])

_STATIC = Path(__file__).parent.parent.parent / "static"
_DEMO_PAGE = _STATIC / "demo.html"
_CHAT_PAGE = _STATIC / "chat.html"


@router.get("/", include_in_schema=False)
async def demo_page() -> FileResponse:
    """Serve the smallest possible manual test page alongside Swagger at /docs."""
    return FileResponse(_DEMO_PAGE)


@router.get("/chat", include_in_schema=False)
async def chat_page() -> FileResponse:
    """Serve the diagnostic chat widget backed by /assistant/diagnose."""
    return FileResponse(_CHAT_PAGE)
