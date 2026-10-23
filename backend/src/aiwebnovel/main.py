"""FastAPI application factory for the AIWebNovel backend foundation."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import Engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from aiwebnovel.ai_writing.composition import compose_ai_workflow, compose_ai_writing
from aiwebnovel.ai_writing.errors import AIWorkflowSchemaRequired
from aiwebnovel.ai_writing.setup_web import AIWorkflowSetupService, create_ai_setup_router
from aiwebnovel.ai_writing.web import create_ai_writing_router
from aiwebnovel.ai_writing.workflow_web import create_ai_workflow_router
from aiwebnovel.backup.composition import compose_backup_service
from aiwebnovel.backup.web import create_backup_router
from aiwebnovel.chapter_planning.web import create_chapter_planning_router
from aiwebnovel.character.application.history_service import (
    CharacterRevisionHistoryQueryService,
)
from aiwebnovel.character.application.services import (
    CharacterCommandService,
    CharacterQueryService,
)
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.web import create_character_history_router, create_character_router
from aiwebnovel.core.config import Settings, get_settings
from aiwebnovel.core.errors import AppError, internal_error_handler, register_error_handlers
from aiwebnovel.core.logging import configure_logging, get_logger
from aiwebnovel.core.middleware import RequestIdMiddleware
from aiwebnovel.db.ai_workflow_upgrade import (
    AIWorkflowUpgradeBusy,
    AIWorkflowUpgradeFailed,
    AIWorkflowUpgradeUnsupported,
    StorageUpgradeChecks,
    upgrade_ai_workflow_database,
)
from aiwebnovel.db.engine import create_database_engine, resolve_database_url
from aiwebnovel.db.health import check_database_health
from aiwebnovel.db.session import create_database_session_factory
from aiwebnovel.domain.time import utc_now
from aiwebnovel.export.web import create_export_router
from aiwebnovel.model_gateway.web import create_model_gateway_router
from aiwebnovel.novel_structure.application.services import (
    NovelStructureCommandService,
    NovelStructureQueryService,
)
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.novel_structure.web import (
    create_chapter_content_router,
    create_novel_structure_router,
)
from aiwebnovel.project.application.services import (
    ProjectCommandService,
    ProjectListQueryService,
    ProjectQueryService,
    ProjectRevisionHistoryQueryService,
)
from aiwebnovel.project.web import create_project_router
from aiwebnovel.security import (
    CSRFMiddleware,
    HostValidationMiddleware,
    InMemorySessionManager,
    RequestLimitsMiddleware,
    SecurityHeadersMiddleware,
    SecurityHealthSnapshot,
    apply_security_headers,
    create_security_router,
    is_security_healthy,
)
from aiwebnovel.security.redaction import redact_text, safe_request_path
from aiwebnovel.storage.health import check_storage_health
from aiwebnovel.storage.initializer import (
    initialize_storage,
    is_reparse_point,
    validate_storage_layout,
)
from aiwebnovel.storage.paths import StoragePaths
from aiwebnovel.story_bible.application.history_service import (
    StoryBibleRevisionHistoryQueryService,
)
from aiwebnovel.story_bible.application.services import (
    StoryBibleCommandService,
    StoryBibleQueryService,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.web import (
    create_story_bible_history_router,
    create_story_bible_router,
)
from aiwebnovel.story_memory.web import create_story_memory_router
from aiwebnovel.usage.web import create_usage_router
from aiwebnovel.web.frontend import FrontendStaticService
from aiwebnovel.workbench.web import create_workbench_router
from aiwebnovel.writing_studio.web import create_writing_studio_router

logger = get_logger("health")

_DEFAULT_APP_NAME = "AIWebNovel"
_DEFAULT_APP_VERSION = "0.0.0"
_DEFAULT_API_PREFIX = "/api/v1"
_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_FRONTEND_DIST_PATH = Path("frontend/dist")
_DEFAULT_CORS_ALLOWED_ORIGINS = ("http://127.0.0.1:5173",)
_DEFAULT_TRUSTED_HOSTS = ("127.0.0.1", "localhost")
_DEFAULT_MAX_REQUEST_BODY_BYTES = 1_048_576
_DEFAULT_SESSION_COOKIE_NAME = "aiwebnovel_session"
_DEFAULT_SESSION_TTL_SECONDS = 28_800
_DEFAULT_SESSION_MAX_ENTRIES = 16
_DEFAULT_CSRF_HEADER_NAME = "X-CSRF-Token"

SettingsProvider = Callable[[], Settings]


def _safe_log_path(value: str) -> str:
    return redact_text(safe_request_path(value))


def _local_documentation_page(title: str) -> HTMLResponse:
    """Return a CSP-compatible schema index without external CDN assets."""
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{title}</title></head><body><main><h1>{title}</h1>"
        '<p><a href="/openapi.json">OpenAPI JSON schema</a></p>'
        "</main></body></html>"
    )


def _security_status(application: FastAPI, settings: Settings | None) -> str:
    """Inspect installed middleware and non-secret settings for readiness."""
    if settings is None:
        return "failed"

    middleware_names: set[str] = set()
    cors_allow_credentials = False
    for middleware in application.user_middleware:
        middleware_class: object = middleware.cls
        if middleware_class is HostValidationMiddleware:
            middleware_names.add("host_validation")
        elif middleware_class is RequestLimitsMiddleware:
            middleware_names.add("request_limits")
        elif middleware_class is CSRFMiddleware:
            middleware_names.add("csrf")
        elif middleware_class is SecurityHeadersMiddleware:
            middleware_names.add("security_headers")
        elif middleware_class is CORSMiddleware:
            middleware_names.add("cors")
            cors_allow_credentials = bool(middleware.kwargs.get("allow_credentials", True))

    snapshot = SecurityHealthSnapshot(
        host=settings.host,
        trusted_hosts=settings.trusted_hosts,
        cors_allowed_origins=settings.cors_allowed_origins,
        cors_allow_credentials=cors_allow_credentials,
        max_request_body_bytes=settings.max_request_body_bytes,
        session_cookie_name=settings.session_cookie_name,
        session_ttl_seconds=settings.session_ttl_seconds,
        session_max_entries=settings.session_max_entries,
        csrf_header_name=settings.csrf_header_name,
        environment=settings.environment,
        expose_api_docs=settings.expose_api_docs,
        middleware_names=frozenset(middleware_names),
        proxy_headers_trusted=bool(getattr(application.state, "proxy_headers_trusted", True)),
        api_docs_explicitly_configured="expose_api_docs" in settings.model_fields_set,
    )
    return "ok" if is_security_healthy(snapshot) else "failed"


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
        resolved_settings.log_level if resolved_settings is not None else _DEFAULT_LOG_LEVEL,
        text_redactor=redact_text,
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
    trusted_hosts = (
        resolved_settings.trusted_hosts if resolved_settings is not None else _DEFAULT_TRUSTED_HOSTS
    )
    max_request_body_bytes = (
        resolved_settings.max_request_body_bytes
        if resolved_settings is not None
        else _DEFAULT_MAX_REQUEST_BODY_BYTES
    )
    session_cookie_name = (
        resolved_settings.session_cookie_name
        if resolved_settings is not None
        else _DEFAULT_SESSION_COOKIE_NAME
    )
    session_ttl_seconds = (
        resolved_settings.session_ttl_seconds
        if resolved_settings is not None
        else _DEFAULT_SESSION_TTL_SECONDS
    )
    session_max_entries = (
        resolved_settings.session_max_entries
        if resolved_settings is not None
        else _DEFAULT_SESSION_MAX_ENTRIES
    )
    csrf_header_name = (
        resolved_settings.csrf_header_name
        if resolved_settings is not None
        else _DEFAULT_CSRF_HEADER_NAME
    )
    expose_api_docs = resolved_settings.expose_api_docs if resolved_settings is not None else False
    session_manager = InMemorySessionManager(
        ttl_seconds=session_ttl_seconds,
        max_entries=session_max_entries,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_engine: Engine | None = None
        application.state.ai_workflow_schema_required = False

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
                    application.state.author_backup_service = compose_backup_service(
                        resolved_settings, storage_paths
                    )
                except Exception as exc:  # noqa: BLE001 - backups stay unavailable safely.
                    logger.info("author backups unavailable error_type=%s", type(exc).__name__)
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
                    from aiwebnovel.character.persistence.history_reader import (
                        SqlAlchemyCharacterRevisionHistoryReader,
                    )
                    from aiwebnovel.character.persistence.list_reader import (
                        SqlAlchemyCharacterListReader,
                    )
                    from aiwebnovel.character.persistence.repository import (
                        SqlAlchemyCharacterRepository,
                    )
                    from aiwebnovel.novel_structure.persistence.repository import (
                        SqlAlchemyNovelStructureRepository,
                    )
                    from aiwebnovel.project.persistence.history import (
                        SqlAlchemyProjectRevisionHistoryReader,
                    )
                    from aiwebnovel.project.persistence.listing import (
                        SqlAlchemyProjectListReader,
                    )
                    from aiwebnovel.project.persistence.repository import (
                        SqlAlchemyProjectRepository,
                    )
                    from aiwebnovel.story_bible.persistence.history_reader import (
                        SqlAlchemyStoryBibleRevisionHistoryReader,
                    )
                    from aiwebnovel.story_bible.persistence.repository import (
                        SqlAlchemyStoryBibleRepository,
                    )

                    application.state.database_engine = runtime_engine
                    application.state.database_session_factory = session_factory
                    project_repository = SqlAlchemyProjectRepository(session_factory)
                    application.state.project_command_service = ProjectCommandService(
                        project_repository
                    )
                    application.state.project_query_service = ProjectQueryService(
                        project_repository
                    )
                    project_list_reader = SqlAlchemyProjectListReader(session_factory)
                    application.state.project_list_query_service = ProjectListQueryService(
                        project_list_reader
                    )
                    project_revision_history_reader = SqlAlchemyProjectRevisionHistoryReader(
                        session_factory
                    )
                    application.state.project_revision_history_query_service = (
                        ProjectRevisionHistoryQueryService(project_revision_history_reader)
                    )
                    story_bible_repository = SqlAlchemyStoryBibleRepository(session_factory)
                    application.state.story_bible_command_service = StoryBibleCommandService(
                        story_bible_repository,
                        utc_now,
                        StoryBibleId.new,
                        StoryBibleRevisionId.new,
                    )
                    application.state.story_bible_query_service = StoryBibleQueryService(
                        story_bible_repository
                    )
                    story_bible_history_reader = SqlAlchemyStoryBibleRevisionHistoryReader(
                        session_factory
                    )
                    application.state.story_bible_revision_history_query_service = (
                        StoryBibleRevisionHistoryQueryService(story_bible_history_reader)
                    )
                    character_repository = SqlAlchemyCharacterRepository(session_factory)
                    character_list_reader = SqlAlchemyCharacterListReader(session_factory)
                    application.state.character_command_service = CharacterCommandService(
                        character_repository,
                        utc_now,
                        CharacterId.new,
                        CharacterRevisionId.new,
                    )
                    application.state.character_query_service = CharacterQueryService(
                        character_repository,
                        character_list_reader,
                    )
                    character_history_reader = SqlAlchemyCharacterRevisionHistoryReader(
                        session_factory
                    )
                    application.state.character_revision_history_query_service = (
                        CharacterRevisionHistoryQueryService(character_history_reader)
                    )
                    novel_structure_repository = SqlAlchemyNovelStructureRepository(session_factory)
                    application.state.novel_structure_command_service = (
                        NovelStructureCommandService(
                            novel_structure_repository,
                            project_repository,
                            utc_now,
                            OutlineId.new,
                            OutlineRevisionId.new,
                            VolumeId.new,
                            VolumeRevisionId.new,
                            ChapterId.new,
                            ChapterRevisionId.new,
                        )
                    )
                    application.state.novel_structure_query_service = NovelStructureQueryService(
                        novel_structure_repository,
                        project_repository,
                    )
                    application.state.ai_writing_service = compose_ai_writing(
                        resolved_settings,
                        application.state.novel_structure_query_service,
                        application.state.project_query_service,
                        application.state.story_bible_query_service,
                        application.state.character_query_service,
                    )
                    try:
                        workflow = compose_ai_workflow(
                            resolved_settings,
                            storage_paths,
                            runtime_engine,
                            session_factory,
                            application.state.novel_structure_query_service,
                            application.state.project_query_service,
                            application.state.story_bible_query_service,
                            application.state.character_query_service,
                        )
                    except AIWorkflowSchemaRequired:
                        application.state.ai_workflow_schema_required = True
                        workflow = None
                    except Exception as exc:  # noqa: BLE001 - keep live/manual writing available.
                        logger.error(
                            "AI workflow initialization failed error_type=%s",
                            type(exc).__name__,
                        )
                        workflow = None
                    if workflow is not None:
                        (
                            application.state.ai_workflow_service,
                            application.state.model_gateway_service,
                            application.state.ai_workflow_runtime,
                            application.state.writing_studio_service,
                            application.state.chapter_planning_service,
                            application.state.story_memory_service,
                            application.state.workbench_service,
                            application.state.usage_ledger_service,
                        ) = workflow

                    # Capture this lifespan's engine: the request cannot choose a path,
                    # database URL or migration revision.
                    setup_engine = runtime_engine
                    assert setup_engine is not None

                    def enable_ai_workflow(engine: Engine = setup_engine) -> None:
                        try:
                            upgrade_ai_workflow_database(
                                engine,
                                storage_paths,
                                StorageUpgradeChecks(validate_storage_layout, is_reparse_point),
                            )
                        except AIWorkflowUpgradeUnsupported:
                            raise AppError(
                                code="AI_WORKFLOW_UPGRADE_UNSUPPORTED",
                                message="The database state does not support this AI upgrade.",
                                status_code=409,
                            ) from None
                        except AIWorkflowUpgradeBusy:
                            raise AppError(
                                code="AI_WORKFLOW_UPGRADE_BUSY",
                                message="The database is busy. Wait and retry AI setup.",
                                status_code=409,
                            ) from None
                        except AIWorkflowUpgradeFailed:
                            raise AppError(
                                code="AI_WORKFLOW_UPGRADE_FAILED",
                                message="AI database backup or upgrade did not complete.",
                                status_code=503,
                            ) from None
                        if application.state.ai_workflow_service is not None:
                            return
                        try:
                            enabled = compose_ai_workflow(
                                resolved_settings,
                                storage_paths,
                                engine,
                                session_factory,
                                application.state.novel_structure_query_service,
                                application.state.project_query_service,
                                application.state.story_bible_query_service,
                                application.state.character_query_service,
                            )
                        except Exception as exc:  # noqa: BLE001 - no author data in errors.
                            logger.error("AI activation failed error_type=%s", type(exc).__name__)
                            enabled = None
                        if enabled is None:
                            raise AppError(
                                code="AI_WORKFLOW_UPGRADE_FAILED",
                                message="Database upgraded, but AI activation failed. Retry setup.",
                                status_code=503,
                            )
                        (
                            application.state.ai_workflow_service,
                            application.state.model_gateway_service,
                            application.state.ai_workflow_runtime,
                            application.state.writing_studio_service,
                            application.state.chapter_planning_service,
                            application.state.story_memory_service,
                            application.state.workbench_service,
                            application.state.usage_ledger_service,
                        ) = enabled
                        application.state.ai_workflow_schema_required = False

                    application.state.ai_workflow_setup_service = AIWorkflowSetupService(
                        enable_ai_workflow
                    )

        application.state.initialized = True
        try:
            yield
        finally:
            application.state.initialized = False
            application.state.project_command_service = None
            application.state.project_list_query_service = None
            application.state.project_query_service = None
            application.state.project_revision_history_query_service = None
            application.state.story_bible_command_service = None
            application.state.story_bible_query_service = None
            application.state.story_bible_revision_history_query_service = None
            application.state.character_command_service = None
            application.state.character_query_service = None
            application.state.character_revision_history_query_service = None
            application.state.novel_structure_command_service = None
            application.state.novel_structure_query_service = None
            application.state.ai_writing_service = None
            application.state.ai_workflow_service = None
            application.state.writing_studio_service = None
            application.state.chapter_planning_service = None
            application.state.story_memory_service = None
            application.state.workbench_service = None
            application.state.usage_ledger_service = None
            application.state.ai_workflow_setup_service = None
            application.state.author_backup_service = None
            application.state.model_gateway_service = None
            if application.state.ai_workflow_runtime is not None:
                application.state.ai_workflow_runtime.close()
                application.state.ai_workflow_runtime = None
            application.state.database_session_factory = None
            session_manager.clear()
            if runtime_engine is not None:
                runtime_engine.dispose()
            application.state.database_engine = None

    application = FastAPI(
        title=app_name,
        version=app_version,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_api_docs else None,
    )
    application.state.settings = resolved_settings
    application.state.configuration_status = "ok" if resolved_settings is not None else "failed"
    application.state.initialized = False
    application.state.storage_paths = None
    application.state.storage_initialized = False
    application.state.database_engine = None
    application.state.database_session_factory = None
    application.state.project_command_service = None
    application.state.project_list_query_service = None
    application.state.project_query_service = None
    application.state.project_revision_history_query_service = None
    application.state.story_bible_command_service = None
    application.state.story_bible_query_service = None
    application.state.story_bible_revision_history_query_service = None
    application.state.character_command_service = None
    application.state.character_query_service = None
    application.state.character_revision_history_query_service = None
    application.state.novel_structure_command_service = None
    application.state.novel_structure_query_service = None
    application.state.ai_writing_service = None
    application.state.ai_workflow_service = None
    application.state.writing_studio_service = None
    application.state.chapter_planning_service = None
    application.state.story_memory_service = None
    application.state.workbench_service = None
    application.state.usage_ledger_service = None
    application.state.ai_workflow_setup_service = None
    application.state.author_backup_service = None
    application.state.ai_workflow_schema_required = False
    application.state.model_gateway_service = None
    application.state.ai_workflow_runtime = None
    application.state.local_session_manager = session_manager
    application.state.proxy_headers_trusted = False
    frontend_service = FrontendStaticService(frontend_dist_path, api_prefix)
    application.state.frontend_service = frontend_service

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "If-Match",
            "X-Request-ID",
            csrf_header_name,
        ],
        expose_headers=["X-Request-ID", "ETag", "Location"],
    )
    application.add_middleware(
        CSRFMiddleware,
        session_manager=session_manager,
        allowed_origins=cors_allowed_origins,
        cookie_name=session_cookie_name,
        csrf_header_name=csrf_header_name,
        api_prefix="/api",
        session_path=f"{api_prefix}/security/session",
    )
    application.add_middleware(
        RequestLimitsMiddleware,
        max_body_bytes=max_request_body_bytes,
        api_prefix="/api",
    )
    application.add_middleware(HostValidationMiddleware, trusted_hosts=trusted_hosts)
    application.add_middleware(SecurityHeadersMiddleware, api_prefix="/api")
    application.add_middleware(RequestIdMiddleware, path_sanitizer=_safe_log_path)
    register_error_handlers(application)

    @application.exception_handler(Exception)
    async def secure_internal_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        response = await internal_error_handler(request, exc)
        apply_security_headers(response.headers, path=request.url.path, api_prefix="/api")
        return response

    application.include_router(
        create_security_router(
            session_manager,
            api_prefix=api_prefix,
            cookie_name=session_cookie_name,
        )
    )
    application.include_router(create_project_router(api_prefix=api_prefix))
    application.include_router(create_story_bible_router(api_prefix=api_prefix))
    application.include_router(create_story_bible_history_router(api_prefix=api_prefix))
    application.include_router(create_character_router(api_prefix=api_prefix))
    application.include_router(create_character_history_router(api_prefix=api_prefix))
    application.include_router(create_novel_structure_router(api_prefix=api_prefix))
    application.include_router(create_chapter_content_router(api_prefix=api_prefix))
    application.include_router(create_ai_writing_router(api_prefix=api_prefix))
    application.include_router(create_ai_workflow_router(api_prefix=api_prefix))
    application.include_router(create_writing_studio_router(api_prefix=api_prefix))
    application.include_router(create_chapter_planning_router(api_prefix=api_prefix))
    application.include_router(create_story_memory_router(api_prefix=api_prefix))
    application.include_router(create_workbench_router(api_prefix=api_prefix))
    application.include_router(create_usage_router(api_prefix=api_prefix))
    application.include_router(create_ai_setup_router(api_prefix=api_prefix))
    application.include_router(create_model_gateway_router(api_prefix=api_prefix))
    application.include_router(create_export_router(api_prefix=api_prefix))
    application.include_router(create_backup_router(api_prefix=api_prefix))

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
        security_status = _security_status(application, resolved_settings)
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
            and security_status == "ok"
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
                    "security": security_status,
                    "storage": storage_status,
                    "database": database_status,
                    "frontend": frontend_status,
                },
            },
        )

    if expose_api_docs:

        @application.get("/docs", include_in_schema=False)
        @application.get("/docs/", include_in_schema=False)
        async def local_api_documentation() -> HTMLResponse:
            return _local_documentation_page("AIWebNovel API documentation")

        @application.get("/redoc", include_in_schema=False)
        @application.get("/redoc/", include_in_schema=False)
        async def local_redoc_documentation() -> HTMLResponse:
            return _local_documentation_page("AIWebNovel API schema")

    else:

        @application.api_route("/docs", methods=["GET", "HEAD"], include_in_schema=False)
        @application.api_route("/redoc", methods=["GET", "HEAD"], include_in_schema=False)
        @application.api_route("/openapi.json", methods=["GET", "HEAD"], include_in_schema=False)
        async def disabled_api_documentation() -> None:
            raise StarletteHTTPException(status_code=404)

    @application.api_route(
        "/docs/{documentation_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    @application.api_route(
        "/redoc/{documentation_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    @application.api_route(
        "/openapi.json/{documentation_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def unavailable_documentation_child(documentation_path: str) -> None:
        del documentation_path
        raise StarletteHTTPException(status_code=404)

    if serve_frontend:

        @application.get("/{frontend_path:path}", include_in_schema=False)
        async def serve_frontend_route(request: Request, frontend_path: str) -> Response:
            return await frontend_service.serve(request, frontend_path)

    return application


app = create_app()
