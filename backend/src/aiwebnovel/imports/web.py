"""Author-only, CSRF-protected manuscript import endpoints."""

from collections.abc import Generator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.core.errors import AppError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class UploadRequest(StrictModel):
    mode: Literal["auto", "single", "chinese", "markdown"]


class ChunkRequest(StrictModel):
    offset: int = Field(ge=0)
    text: str = Field(max_length=100_000)


class EmptyRequest(StrictModel):
    pass


class Part(StrictModel):
    title: str
    start: int = Field(ge=0)
    body_start: int = Field(ge=0)
    end: int = Field(ge=0)


class EditRequest(StrictModel):
    expected_version: int = Field(ge=1)
    chapters: list[Part] = Field(min_length=1, max_length=500)


class CommitRequest(StrictModel):
    preview_version: int = Field(ge=1)
    source_sha256: str = Field(min_length=64, max_length=64)
    idempotency_key: str
    title: str


def import_session(request: Request, response: Response) -> Generator[Session, None, None]:
    response.headers["Cache-Control"] = "no-store"
    factory = getattr(request.app.state, "database_session_factory", None)
    if factory is None or getattr(request.app.state, "ai_workflow_schema_required", False):
        raise AppError(
            code="IMPORT_UNAVAILABLE",
            message="Upgrade the database before importing.",
            status_code=503,
        )
    session = factory()
    try:
        if not inspect(session.get_bind()).has_table("import_previews"):
            raise AppError(
                code="IMPORT_UNAVAILABLE",
                message="Upgrade the database before importing.",
                status_code=503,
            )
        yield session
    finally:
        session.close()


def create_import_router(api_prefix: str) -> APIRouter:
    router = APIRouter(prefix=api_prefix + "/imports", tags=["imports"])

    @router.post("/uploads")
    def begin(
        body: UploadRequest,
        session: Annotated[Session, Depends(import_session)],
        _: Annotated[None, Depends(require_json)],
    ) -> dict[str, str]:
        from aiwebnovel.imports.service import start_upload

        return {"upload_id": start_upload(session, body.mode)}

    @router.put("/uploads/{upload_id}/chunks")
    def chunk(
        upload_id: str,
        body: ChunkRequest,
        session: Annotated[Session, Depends(import_session)],
        _: Annotated[None, Depends(require_json)],
    ) -> dict[str, int]:
        from aiwebnovel.imports.service import append_chunk

        return {"next_offset": append_chunk(session, upload_id, body.offset, body.text)}

    @router.post("/uploads/{upload_id}/finish")
    def finish(
        upload_id: str,
        body: EmptyRequest,
        session: Annotated[Session, Depends(import_session)],
        _: Annotated[None, Depends(require_json)],
    ) -> dict[str, object]:
        from aiwebnovel.imports.service import finish_upload

        return finish_upload(session, upload_id)

    @router.get("/{preview_id}/preview")
    def get_preview(
        preview_id: str, session: Annotated[Session, Depends(import_session)]
    ) -> dict[str, object]:
        from aiwebnovel.imports.service import _read, render

        record = _read(session, preview_id)
        if record.version == 0:
            raise AppError(
                code="IMPORT_CONFLICT", message="The upload is not finished.", status_code=409
            )
        return render(record)

    @router.put("/{preview_id}/preview")
    def edit(
        preview_id: str,
        body: EditRequest,
        session: Annotated[Session, Depends(import_session)],
        _: Annotated[None, Depends(require_json)],
    ) -> dict[str, object]:
        from aiwebnovel.imports.service import edit_preview

        return edit_preview(
            session,
            preview_id,
            body.expected_version,
            [part.model_dump() for part in body.chapters],
        )

    @router.post("/{preview_id}/commit")
    def save(
        preview_id: str,
        body: CommitRequest,
        request: Request,
        session: Annotated[Session, Depends(import_session)],
        _: Annotated[None, Depends(require_json)],
    ) -> dict[str, object]:
        from aiwebnovel.imports.service import commit

        return commit(
            session,
            preview_id,
            body.preview_version,
            body.source_sha256,
            body.idempotency_key,
            body.title,
            request.app.state.import_project_store,
        )

    @router.get("/{preview_id}/receipt")
    def get_receipt(
        preview_id: str, request: Request, session: Annotated[Session, Depends(import_session)]
    ) -> dict[str, object]:
        from aiwebnovel.imports.persistence import ImportReceiptRecord
        from aiwebnovel.imports.service import receipt_view

        receipt = session.scalar(
            select(ImportReceiptRecord).where(ImportReceiptRecord.preview_id == preview_id)
        )
        if receipt is None:
            raise AppError(
                code="IMPORT_NOT_FOUND", message="Import receipt not found.", status_code=404
            )
        return receipt_view(session, receipt, request.app.state.import_project_store)

    return router
