"""Application router composition."""

from fastapi import APIRouter

from app.api.routes import chat, complaints, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(complaints.router)
