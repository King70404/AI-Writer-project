"""Author backup HTTP endpoints; writes require the standard Session/CSRF protection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.backup.archive import (
    BackupArchiveError,
    BackupManifest,
    DatabaseSummary,
    archive_name,
    is_backup_id,
)
from aiwebnovel.backup.service import (
    AuthorBackupService,
    BackupBusy,
    BackupNotFound,
    BackupServiceError,
    BackupUnavailable,
    RestoreTargetInvalid,
    RestoreTargetNotEmpty,
)
from aiwebnovel.core.errors import AppError

_NO_STORE = "no-store"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CreateBackupRequest(Strict):
    pass


class VerifyBackupRequest(Strict):
    pass


class RestoreBackupRequest(Strict):
    target_name: Annotated[str, Field(min_length=1, max_length=64)]
    confirm_new_copy: bool


class ContentCounts(Strict):
    projects: int
    chapters: int
    chapter_revisions: int
    confirmed_facts: int
    workflow_runs: int


class BackupSummaryResponse(Strict):
    schema_revision: str
    requires_upgrade: bool
    counts: ContentCounts


class BackupItemResponse(Strict):
    backup_id: str
    file_bytes: int
    readable: bool
    created_at: str | None
    summary: BackupSummaryResponse | None


class BackupListResponse(Strict):
    items: list[BackupItemResponse]


class VerifyBackupResponse(Strict):
    backup_id: str
    status: Literal["valid", "corrupt", "incompatible"]
    problem: str | None
    summary: BackupSummaryResponse | None


class RestoreBackupResponse(Strict):
    backup_id: str
    target_name: str
    summary: BackupSummaryResponse


def _summary(summary: DatabaseSummary) -> BackupSummaryResponse:
    return BackupSummaryResponse(
        schema_revision=summary.schema_revision,
        requires_upgrade=summary.requires_upgrade,
        counts=ContentCounts(**dict(summary.counts)),
    )


def _item(backup_id: str, file_bytes: int, manifest: BackupManifest | None) -> BackupItemResponse:
    return BackupItemResponse(
        backup_id=backup_id,
        file_bytes=file_bytes,
        readable=manifest is not None,
        created_at=None if manifest is None else manifest.created_at,
        summary=None if manifest is None else _summary(manifest.summary),
    )


_ERRORS: tuple[tuple[type[Exception], int, str, bool], ...] = (
    (BackupBusy, 409, "Another backup task is running. Wait and retry.", True),
    (BackupNotFound, 404, "The backup does not exist.", False),
    (BackupUnavailable, 503, "Backups are unavailable for the current data.", False),
    (RestoreTargetInvalid, 422, "Choose a plain new folder name.", False),
    (RestoreTargetNotEmpty, 409, "The restore folder already exists and is not empty.", False),
)


def _raise(exc: Exception) -> NoReturn:
    for error_type, status, message, retryable in _ERRORS:
        if isinstance(exc, error_type):
            raise AppError(
                code=getattr(exc, "code", "BACKUP_FAILED"),
                message=message,
                status_code=status,
                retryable=retryable,
            ) from None
    if isinstance(exc, BackupArchiveError):
        incompatible = exc.code == "BACKUP_INCOMPATIBLE"
        raise AppError(
            code=exc.code,
            message="The backup is not supported by this version."
            if incompatible
            else "The backup failed integrity verification.",
            status_code=409 if incompatible else 422,
        ) from None
    raise AppError(
        code="BACKUP_FAILED",
        message="The backup operation did not complete; current data is unchanged.",
        status_code=503,
    ) from None


def _service(request: Request) -> AuthorBackupService:
    service = getattr(request.app.state, "author_backup_service", None)
    if not isinstance(service, AuthorBackupService):
        raise AppError(
            code="BACKUP_UNAVAILABLE",
            message="Backups are unavailable for the current data.",
            status_code=503,
        )
    return service


def _backup_id(backup_id: str) -> str:
    if not is_backup_id(backup_id):
        raise AppError(
            code="BACKUP_NOT_FOUND", message="The backup does not exist.", status_code=404
        )
    return backup_id


async def _call[T](operation: Callable[[], T]) -> T:
    try:
        return await run_in_threadpool(operation)
    except (BackupServiceError, BackupArchiveError) as exc:
        _raise(exc)


def create_backup_router(*, api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix + "/backups", tags=["Author Backups"])

    @router.get("", response_model=BackupListResponse)
    async def list_backups(request: Request, response: Response) -> BackupListResponse:
        response.headers["Cache-Control"] = _NO_STORE
        service = _service(request)
        listings = await _call(service.list)
        return BackupListResponse(
            items=[_item(item.backup_id, item.file_bytes, item.manifest) for item in listings]
        )

    @router.post("", response_model=BackupItemResponse, status_code=201)
    async def create_backup(
        _payload: CreateBackupRequest,
        request: Request,
        response: Response,
        _json: Annotated[None, Depends(require_json)],
    ) -> BackupItemResponse:
        response.headers["Cache-Control"] = _NO_STORE
        service = _service(request)
        created = await _call(service.create)
        return _item(created.backup_id, created.file_bytes, created.manifest)

    @router.post("/{backup_id}/verify", response_model=VerifyBackupResponse)
    async def verify_backup(
        backup_id: str,
        _payload: VerifyBackupRequest,
        request: Request,
        response: Response,
        _json: Annotated[None, Depends(require_json)],
    ) -> VerifyBackupResponse:
        response.headers["Cache-Control"] = _NO_STORE
        service = _service(request)
        identifier = _backup_id(backup_id)
        result = await _call(lambda: service.verify(identifier))
        return VerifyBackupResponse(
            backup_id=result.backup_id,
            status=result.status,
            problem=result.problem,
            summary=None if result.manifest is None else _summary(result.manifest.summary),
        )

    @router.get("/{backup_id}/download", response_class=FileResponse)
    async def download_backup(backup_id: str, request: Request) -> FileResponse:
        service = _service(request)
        identifier = _backup_id(backup_id)
        path = await _call(lambda: service.download_path(identifier))
        return FileResponse(
            path,
            media_type="application/zip",
            filename=archive_name(identifier),
            headers={"Cache-Control": _NO_STORE},
        )

    @router.post("/{backup_id}/restore", response_model=RestoreBackupResponse)
    async def restore_backup(
        backup_id: str,
        payload: RestoreBackupRequest,
        request: Request,
        response: Response,
        _json: Annotated[None, Depends(require_json)],
    ) -> RestoreBackupResponse:
        response.headers["Cache-Control"] = _NO_STORE
        if not payload.confirm_new_copy:
            raise AppError(
                code="RESTORE_CONFIRMATION_REQUIRED",
                message="Confirm restoring into a new independent copy first.",
                status_code=422,
            )
        service = _service(request)
        identifier = _backup_id(backup_id)
        result = await _call(lambda: service.restore_to_sibling(identifier, payload.target_name))
        return RestoreBackupResponse(
            backup_id=result.backup_id,
            target_name=result.target_root.name,
            summary=_summary(result.summary),
        )

    return router
