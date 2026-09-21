"""Minimal static test page for manually demonstrating the assistant."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["demo-ui"])

_DEMO_PAGE = Path(__file__).parent.parent.parent / "static" / "demo.html"


@router.get("/", include_in_schema=False)
async def demo_page() -> FileResponse:
    """Serve the smallest possible manual test page alongside Swagger at /docs."""
    return FileResponse(_DEMO_PAGE)
