"""Health endpoint."""

from fastapi import APIRouter, Request

from app.domain.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Return minimal liveness information."""
    settings = request.app.state.settings
    return HealthResponse(status="ok", service=settings.service_name, version=settings.version)
