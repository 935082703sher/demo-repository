"""Application router composition."""

from fastapi import APIRouter

from app.api.routes import (
    admin,
    assistant,
    case,
    chat,
    complaints,
    demo_ui,
    diagnostics,
    health,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(complaints.router)
api_router.include_router(assistant.router)
api_router.include_router(case.router)
api_router.include_router(diagnostics.router)
api_router.include_router(admin.router)
api_router.include_router(demo_ui.router)
