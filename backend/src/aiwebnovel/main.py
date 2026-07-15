"""FastAPI application factory for the AIWebNovel backend foundation."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import Engine

from aiwebnovel.core.config import Settings, get_settings
from aiwebnovel.core.errors import register_error_handlers
from aiwebnovel.core.logging import configure_logging, get_logger
from aiwebnovel.core.middleware import RequestIdMiddleware
from aiwebnovel.db.engine import create_database_engine, resolve_database_url
from aiwebnovel.db.health import check_database_health
from aiwebnovel.db.session import create_database_session_factory
from aiwebnovel.storage.health import check_storage_health
from aiwebnovel.storage.initializer import initialize_storage
from aiwebnovel.storage.paths import StoragePaths
from aiwebnovel.web.frontend import FrontendStaticService

logger = get_logger("health")

_DEFAULT_APP_NAME = "AIWebNovel"
_DEFAULT_APP_VERSION = "0.0.0"
_DEFAULT_API_PREFIX = "/api/v1"
_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_FRONTEND_DIST_PATH = Path("frontend/dist")
_DEFAULT_CORS_ALLOWED_ORIGINS = ("http://127.0.0.1:5173",)

SettingsProvider = Callable[[], Settings]


def create_app(
    settings: Settings | None = None,
    *,
    settings_provider: SettingsProvider = get_settings,
) -> FastAPI:
    """Build one independent application, degrading safely on configuration failure."""
    configuration_error_type: str | None = None
    if settings is not None:
        resolved_settings = settings
    else:
        try:
            resolved_settings = settings_provider()
        except Exception as exc:  # noqa: BLE001 - live must survive invalid configuration.
            resolved_settings = None
            configuration_error_type = type(exc).__name__

    configure_logging(
        resolved_settings.log_level if resolved_settings is not None else _DEFAULT_LOG_LEVEL
    )
    if configuration_error_type is not None:
        logger.error(
            "application configuration unavailable error_type=%s",
            configuration_error_type,
        )

    app_name = resolved_settings.app_name if resolved_settings is not None else _DEFAULT_APP_NAME
    app_version = (
        resolved_settings.app_version if resolved_settings is not None else _DEFAULT_APP_VERSION
    )
    api_prefix = (
        resolved_settings.api_prefix if resolved_settings is not None else _DEFAULT_API_PREFIX
    )
    cors_allowed_origins = (
        resolved_settings.cors_allowed_origins
        if resolved_settings is not None
        else _DEFAULT_CORS_ALLOWED_ORIGINS
    )
    frontend_dist_path = (
        resolved_settings.frontend_dist_path
        if resolved_settings is not None
        else _DEFAULT_FRONTEND_DIST_PATH
    )
    serve_frontend = resolved_settings.serve_frontend if resolved_settings is not None else False

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_engine: Engine | None = None

        if resolved_settings is not None:
            try:
                storage_paths = StoragePaths.from_settings(resolved_settings)
                application.state.storage_paths = storage_paths
                initialize_storage(storage_paths)
                check_storage_health(storage_paths)
            except Exception as exc:  # noqa: BLE001 - readiness degrades without path leakage.
                logger.error(
                    "storage initialization failed error_type=%s",
                    type(exc).__name__,
                )
            else:
                application.state.storage_initialized = True
                try:
                    database_url = resolve_database_url(resolved_settings, storage_paths)
                    runtime_engine = create_database_engine(
                        resolved_settings,
                        database_url,
                        storage_paths=storage_paths,
                    )
                    session_factory = create_database_session_factory(runtime_engine)
                except Exception as exc:  # noqa: BLE001 - readiness reports database failure.
                    logger.error(
                        "database initialization failed error_type=%s",
                        type(exc).__name__,
                    )
                    if runtime_engine is not None:
                        runtime_engine.dispose()
                        runtime_engine = None
                else:
                    application.state.database_engine = runtime_engine
                    application.state.database_session_factory = session_factory

        application.state.initialized = True
        try:
            yield
        finally:
            application.state.initialized = False
            application.state.database_session_factory = None
            if runtime_engine is not None:
                runtime_engine.dispose()
            application.state.database_engine = None

    application = FastAPI(
        title=app_name,
        version=app_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.configuration_status = "ok" if resolved_settings is not None else "failed"
    application.state.initialized = False
    application.state.storage_paths = None
    application.state.storage_initialized = False
    application.state.database_engine = None
    application.state.database_session_factory = None
    frontend_service = FrontendStaticService(frontend_dist_path, api_prefix)
    application.state.frontend_service = frontend_service

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestIdMiddleware)
    register_error_handlers(application)

    @application.get(f"{api_prefix}/health/live")
    async def live() -> dict[str, str]:
        return {
            "status": "ok",
            "service": app_name,
            "version": app_version,
        }

    @application.get(f"{api_prefix}/health/ready")
    def ready() -> JSONResponse:
        configuration_status = application.state.configuration_status
        application_status = "ok" if application.state.initialized is True else "failed"
        storage_status = "failed"
        database_status = "failed"

        storage_paths = application.state.storage_paths
        if application.state.storage_initialized is True and isinstance(
            storage_paths, StoragePaths
        ):
            try:
                check_storage_health(storage_paths)
            except Exception as exc:  # noqa: BLE001 - readiness degrades safely.
                logger.error(
                    "storage readiness check failed error_type=%s",
                    type(exc).__name__,
                )
            else:
                storage_status = "ok"

        engine = application.state.database_engine
        if storage_status == "ok" and engine is not None:
            try:
                check_database_health(engine)
            except Exception as exc:  # noqa: BLE001 - readiness must degrade safely.
                logger.error(
                    "database readiness check failed error_type=%s",
                    type(exc).__name__,
                )
            else:
                database_status = "ok"

        frontend_status = frontend_service.status() if serve_frontend else "not_required"
        is_ready = (
            configuration_status == "ok"
            and application_status == "ok"
            and storage_status == "ok"
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
                    "storage": storage_status,
                    "database": database_status,
                    "frontend": frontend_status,
                },
            },
        )

    if serve_frontend:

        @application.get("/{frontend_path:path}", include_in_schema=False)
        async def serve_frontend_route(request: Request, frontend_path: str) -> Response:
            return await frontend_service.serve(request, frontend_path)

    return application


app = create_app()
