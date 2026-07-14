"""FastAPI application factory for the AIWebNovel backend foundation."""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from aiwebnovel.core.config import Settings, get_settings
from aiwebnovel.core.errors import register_error_handlers
from aiwebnovel.core.logging import configure_logging
from aiwebnovel.core.middleware import RequestIdMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build one independent application instance without business side effects."""
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
    )
    application.state.settings = resolved_settings
    application.state.initialized = False

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
    async def ready() -> JSONResponse:
        configuration_status = (
            "ok" if isinstance(application.state.settings, Settings) else "failed"
        )
        application_status = (
            "ok" if application.state.initialized is True else "failed"
        )
        is_ready = configuration_status == "ok" and application_status == "ok"
        return JSONResponse(
            status_code=200 if is_ready else 503,
            content={
                "status": "ready" if is_ready else "not_ready",
                "checks": {
                    "configuration": configuration_status,
                    "application": application_status,
                },
            },
        )

    application.state.initialized = True
    return application


app = create_app()
