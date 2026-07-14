"""FastAPI application factory for the AIWebNovel backend foundation."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from aiwebnovel.core.config import Settings, get_settings
from aiwebnovel.core.errors import register_error_handlers
from aiwebnovel.core.logging import configure_logging, get_logger
from aiwebnovel.core.middleware import RequestIdMiddleware
from aiwebnovel.db.engine import create_database_engine
from aiwebnovel.db.health import check_database_health
from aiwebnovel.db.session import create_database_session_factory
from aiwebnovel.web.frontend import FrontendStaticService

logger = get_logger("health")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build one independent application instance without business side effects."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(resolved_settings)
        application.state.database_engine = engine
        application.state.database_session_factory = create_database_session_factory(engine)
        application.state.initialized = True
        try:
            yield
        finally:
            application.state.initialized = False
            application.state.database_session_factory = None
            engine.dispose()
            application.state.database_engine = None

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.initialized = False
    application.state.database_engine = None
    application.state.database_session_factory = None
    frontend_service = FrontendStaticService(
        resolved_settings.frontend_dist_path,
        resolved_settings.api_prefix,
    )
    application.state.frontend_service = frontend_service

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestIdMiddleware)
    register_error_handlers(application)

    @application.get(f"{resolved_settings.api_prefix}/health/live")
    async def live() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved_settings.app_name,
            "version": resolved_settings.app_version,
        }

    @application.get(f"{resolved_settings.api_prefix}/health/ready")
    def ready() -> JSONResponse:
        configuration_status = (
            "ok" if isinstance(application.state.settings, Settings) else "failed"
        )
        application_status = "ok" if application.state.initialized is True else "failed"
        database_status = "failed"
        frontend_status = (
            frontend_service.status() if resolved_settings.serve_frontend else "not_required"
        )
        engine = application.state.database_engine
        if engine is not None:
            try:
                check_database_health(engine)
            except Exception as exc:  # noqa: BLE001 - readiness must degrade safely.
                logger.error(
                    "database readiness check failed error_type=%s",
                    type(exc).__name__,
                )
            else:
                database_status = "ok"

        is_ready = (
            configuration_status == "ok"
            and application_status == "ok"
            and database_status == "ok"
            and frontend_status in {"ok", "not_required"}
        )
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={
                "status": "ready" if is_ready else "not_ready",
                "checks": {
                    "configuration": configuration_status,
                    "application": application_status,
                    "database": database_status,
                    "frontend": frontend_status,
                },
            },
        )

    if resolved_settings.serve_frontend:

        @application.get("/{frontend_path:path}", include_in_schema=False)
        async def serve_frontend(request: Request, frontend_path: str) -> Response:
            return await frontend_service.serve(request, frontend_path)

    return application


app = create_app()
