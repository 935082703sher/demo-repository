"""FastAPI application factory for RTMC AI Assistant Demo 2."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError as FastAPIValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.domain.schemas import ErrorBody, ErrorResponse
from app.providers.base import LLMProvider
from app.providers.configured import build_configured_provider
from app.repositories.usage_repository import (
    InMemoryRateLimitRepository,
    InMemoryUsageRepository,
    RateLimitRepository,
    UsageRepository,
)
from app.services.approved_links import stage3b_link_registry
from app.services.assistant import AssistantService
from app.services.classifier import RequestClassifier
from app.services.complaint_drafts import ComplaintDraftService
from app.services.complaint_workflow_adapter import GovernedComplaintWorkflowAdapter
from app.services.generation import GroundedGenerationService
from app.services.governed_complaint_orchestrator import GovernedComplaintOrchestrator
from app.services.grounding import GroundingValidator
from app.services.guardrails import Guardrails
from app.services.knowledge import KnowledgeService
from app.services.scope import ScopeService
from app.services.usage_limits import RequestRateLimitService, UsageLimitService

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    knowledge_path: Path | None = None,
    usage_repository: UsageRepository | None = None,
    rate_limit_repository: RateLimitRepository | None = None,
) -> FastAPI:
    """Build an isolated application instance suitable for tests or local serving."""
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)
    data_path = knowledge_path or Path(__file__).parent / "data" / "approved_faq.demo.json"

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("event=service_start environment=%s", app_settings.environment)
        yield
        logger.info("event=service_stop")

    app = FastAPI(
        title="RTMC AI Assistant Demo 2",
        version=app_settings.version,
        description=(
            "Local controlled demo only. It cannot register an official appeal "
            "or generate an official case number."
        ),
        lifespan=lifespan,
    )
    if app_settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_allowed_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "X-Request-ID"],
            allow_credentials=False,
        )
    knowledge = KnowledgeService.from_json(data_path)
    usage_limits = UsageLimitService(
        usage_repository if usage_repository is not None else InMemoryUsageRepository(),
        limit=app_settings.llm_generation_limit_per_session,
        window_seconds=app_settings.llm_quota_window_seconds,
    )
    selected_provider = (
        provider if provider is not None else build_configured_provider(app_settings)
    )
    app.state.settings = app_settings
    app.state.provider = selected_provider
    app.state.usage_limits = usage_limits
    legacy_drafts = ComplaintDraftService(app_settings.privacy_notice_version)
    governed_adapter = GovernedComplaintWorkflowAdapter(
        legacy=legacy_drafts,
        enabled=app_settings.governed_complaint_workflow_enabled,
        privacy_notice_version=app_settings.privacy_notice_version,
        consent_wording_version=app_settings.governed_consent_wording_version,
    )
    app.state.assistant = AssistantService(
        classifier=RequestClassifier(),
        guardrails=Guardrails(),
        scope=ScopeService(),
        knowledge=knowledge,
        generation=GroundedGenerationService(
            selected_provider,
            usage_limits,
            timeout_seconds=app_settings.llm_timeout_seconds,
            max_retries=app_settings.llm_max_retries,
            input_cost_per_million=app_settings.llm_input_cost_per_million,
            output_cost_per_million=app_settings.llm_output_cost_per_million,
        ),
        grounding=GroundingValidator(),
        usage_limits=usage_limits,
        rate_limits=RequestRateLimitService(
            (
                rate_limit_repository
                if rate_limit_repository is not None
                else InMemoryRateLimitRepository()
            ),
            limit=app_settings.request_rate_limit_per_minute,
        ),
        approved_support_phone=app_settings.approved_support_phone,
        approved_contact_url=(
            str(app_settings.approved_contact_url)
            if app_settings.approved_contact_url is not None
            else None
        ),
        handoff_observer=(
            governed_adapter.observe_legacy_handoff
            if app_settings.governed_complaint_workflow_enabled
            else None
        ),
    )
    app.state.drafts = governed_adapter
    app.state.governed_complaint_workflow = governed_adapter
    app.state.governed_complaint_orchestrator = (
        GovernedComplaintOrchestrator(
            adapter=governed_adapter,
            privacy_notice_version=app_settings.privacy_notice_version,
            consent_wording_version=app_settings.governed_consent_wording_version,
        )
        if app_settings.governed_complaint_workflow_enabled
        else None
    )
    app.state.approved_links = stage3b_link_registry()

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_id=%s endpoint=%s outcome=unhandled_error",
                request_id,
                request.url.path,
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = str(request_id)
        logger.info(
            "request_id=%s endpoint=%s method=%s status=%s duration_ms=%.2f",
            request_id,
            request.url.path,
            request.method,
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(
                code=exc.code,
                message=exc.message,
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(FastAPIValidationError)
    async def validation_error_handler(
        request: Request,
        exc: FastAPIValidationError,
    ) -> JSONResponse:
        details = [
            {
                "location": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        body = ErrorResponse(
            error=ErrorBody(
                code="request_validation_error",
                message="The request did not match the API contract",
                request_id=request.state.request_id,
                details=details,
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, _: Exception) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorBody(
                code="internal_error",
                message="The service could not complete the request",
                request_id=request.state.request_id,
            )
        )
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))

    app.include_router(api_router)
    return app


def _request_id(value: str | None) -> UUID:
    if value is not None:
        try:
            return UUID(value)
        except ValueError:
            pass
    return uuid4()


app = create_app()
