"""A bounded, author-confirmed manuscript import transaction."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.time import utc_now
from aiwebnovel.imports.persistence import ImportPreviewRecord, ImportReceiptRecord
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.novel_structure.persistence.mappers import (
    chapter_aggregate_to_records,
    volume_aggregate_to_records,
)
from aiwebnovel.novel_structure.transitions import create_initial_chapter, create_initial_volume
from aiwebnovel.novel_structure.values import (
    ManuscriptContent,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.deletion import is_deleted_project_title, is_reserved_project_title
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.transitions import create_initial_project


class ProjectImportStore(Protocol):
    def persist(self, session: Session, project: ProjectAggregate) -> None: ...
    def current_title(self, session: Session, project_id: str) -> str | None: ...


MAX_BYTES = 10 * 1024 * 1024
MAX_CHUNKSIZE = 100_000
MAX_CHAPTERS = 500
_PATTERN_CHINESE = re.compile(r"^\s*第[0-9零\u3007一二三四五六七八九十百千万两]+[章回节][^\r\n]*$")
_PATTERN_MARKDOWN = re.compile(r"^#{1,2}\s+[^\r\n]+$")


def problem(code: str, message: str, status: int = 422) -> AppError:
    return AppError(code=code, message=message, status_code=status)


def valid_id(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise problem("IMPORT_INVALID", "Invalid import identifier.") from None
    return value


def _digest(value: str) -> str:
    try:
        return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()
    except UnicodeEncodeError:
        raise problem("IMPORT_INVALID_ENCODING", "The text is not valid UTF-8.") from None


def _bytes(value: str) -> int:
    try:
        return len(value.encode("utf-8", "strict"))
    except UnicodeEncodeError:
        raise problem("IMPORT_INVALID_ENCODING", "The text is not valid UTF-8.") from None


def _chapters(source: str, mode: str) -> list[dict[str, object]]:
    found: list[tuple[int, int, str]] = []
    offset = 0
    for line in source.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        chinese = bool(_PATTERN_CHINESE.fullmatch(content))
        markdown = bool(_PATTERN_MARKDOWN.fullmatch(content))
        if (mode in ("auto", "chinese") and chinese) or (mode in ("auto", "markdown") and markdown):
            title = re.sub(r"^#{1,2}\s+", "", content).strip()
            try:
                NovelStructureTitle(title)
            except DomainError:
                raise problem(
                    "IMPORT_INVALID_CHAPTER", "A detected heading is invalid or too long."
                ) from None
            found.append((offset, offset + len(line), title))
        offset += len(line)
    if mode == "single":
        found = []
    result: list[dict[str, object]] = []
    if not found:
        return [{"title": "正文", "start": 0, "body_start": 0, "end": len(source)}]
    if found[0][0] > 0:
        result.append({"title": "序言", "start": 0, "body_start": 0, "end": found[0][0]})
    for i, (start, body_start, title) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(source)
        result.append({"title": title, "start": start, "body_start": body_start, "end": end})
    if len(result) > MAX_CHAPTERS:
        raise problem("IMPORT_TOO_MANY_CHAPTERS", "The import exceeds 500 chapters.")
    return result


def validate_parts(source: str, parts: list[dict[str, object]]) -> None:
    if not 1 <= len(parts) <= MAX_CHAPTERS:
        raise problem("IMPORT_INVALID", "A preview must contain 1 to 500 chapters.")
    expected = 0
    for index, part in enumerate(parts, 1):
        if set(part) != {"title", "start", "body_start", "end"}:
            raise problem("IMPORT_INVALID", "Invalid chapter boundaries.")
        title, start, body_start, end = (part[k] for k in ("title", "start", "body_start", "end"))
        if type(title) is not str or any(type(v) is not int for v in (start, body_start, end)):
            raise problem("IMPORT_INVALID", "Invalid chapter boundaries.")
        assert isinstance(start, int) and isinstance(body_start, int) and isinstance(end, int)
        if start != expected or not start <= body_start <= end <= len(source):
            raise problem("IMPORT_INVALID", "Chapter boundaries must cover the source in order.")
        prefix = source[start:body_start]
        if prefix:
            lines = prefix.splitlines(keepends=True)
            if len(lines) != 1 or not (
                _PATTERN_CHINESE.fullmatch(lines[0].rstrip("\r\n"))
                or _PATTERN_MARKDOWN.fullmatch(lines[0].rstrip("\r\n"))
            ):
                raise problem(
                    "IMPORT_INVALID", "Only a recognized heading may be removed from the source."
                )
        try:
            NovelStructureTitle(title)
            ManuscriptContent(source[body_start:end])
        except DomainError:
            raise problem(
                "IMPORT_INVALID_CHAPTER", f"Chapter {index} has invalid title or content."
            ) from None
        expected = end
    if expected != len(source):
        raise problem("IMPORT_INVALID", "Chapter boundaries must cover the source in order.")


def _read(session: Session, preview_id: str) -> ImportPreviewRecord:
    record = session.get(ImportPreviewRecord, valid_id(preview_id))
    if record is None:
        raise problem("IMPORT_NOT_FOUND", "Import preview not found.", 404)
    expiry = record.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= datetime.now(UTC):
        raise problem("IMPORT_PREVIEW_EXPIRED", "Import preview expired; start a new preview.", 409)
    return record


def render(record: ImportPreviewRecord) -> dict[str, object]:
    return {
        "preview_id": record.id,
        "version": record.version,
        "source_sha256": record.source_sha256,
        "source_text": record.source_text,
        "expires_at": record.expires_at.isoformat(),
        "original_line_endings_normalized": "\r" in record.source_text,
        "chapters": [
            {
                **part,
                "body": record.source_text[cast(int, part["body_start"]) : cast(int, part["end"])],
            }
            for part in record.chapters
        ],
    }


def start_upload(session: Session, mode: str) -> str:
    if mode not in {"auto", "single", "chinese", "markdown"}:
        raise problem("IMPORT_INVALID", "Invalid heading mode.")
    session.execute(text("BEGIN IMMEDIATE"))
    expired = session.scalars(
        select(ImportPreviewRecord)
        .where(
            ImportPreviewRecord.expires_at <= datetime.now(UTC),
            ImportPreviewRecord.id.not_in(select(ImportReceiptRecord.preview_id)),
        )
        .limit(25)
    ).all()
    for stale in expired:
        session.delete(stale)
    token = str(uuid4())
    session.add(
        ImportPreviewRecord(
            id=token,
            source_sha256="",
            source_text="",
            chapters=[{"mode": mode}],
            version=0,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    session.commit()
    return token


def append_chunk(session: Session, upload_id: str, offset: int, value: str) -> int:
    if len(value) > MAX_CHUNKSIZE or offset < 0:
        raise problem("IMPORT_INVALID", "Invalid upload chunk.")
    session.execute(text("BEGIN IMMEDIATE"))
    record = _read(session, upload_id)
    if record.version != 0:
        raise problem("IMPORT_CONFLICT", "The upload is already finished.", 409)
    current = record.source_text
    if offset < len(current):
        if current[offset : offset + len(value)] == value:
            return offset + len(value)
        raise problem("IMPORT_CONFLICT", "Upload chunk conflicts with earlier text.", 409)
    if offset != len(current):
        raise problem("IMPORT_CONFLICT", "Upload chunks must be sent in order.", 409)
    combined = current + value
    if _bytes(combined) > MAX_BYTES:
        raise problem("IMPORT_TOO_LARGE", "The source exceeds 10 MiB.", 413)
    record.source_text = combined
    session.commit()
    return len(combined)


def finish_upload(session: Session, upload_id: str) -> dict[str, object]:
    session.execute(text("BEGIN IMMEDIATE"))
    record = _read(session, upload_id)
    if record.version != 0:
        return render(record)
    source = record.source_text
    if source.startswith("\ufeff"):
        source = source[1:]
    mode = str(record.chapters[0]["mode"])
    parts = _chapters(source, mode)
    validate_parts(source, parts)
    record.source_text = source
    record.chapters = parts
    record.source_sha256 = _digest(source)
    record.version = 1
    session.commit()
    return render(record)


def edit_preview(
    session: Session, preview_id: str, version: int, chapters: list[dict[str, object]]
) -> dict[str, object]:
    session.execute(text("BEGIN IMMEDIATE"))
    record = _read(session, preview_id)
    if record.version != version or record.version == 0:
        raise problem("IMPORT_CONFLICT", "The import preview has changed.", 409)
    if (
        session.scalar(
            select(ImportReceiptRecord).where(ImportReceiptRecord.preview_id == record.id)
        )
        is not None
    ):
        raise problem("IMPORT_CONFLICT", "The import has already been committed.", 409)
    validate_parts(record.source_text, chapters)
    record.chapters = chapters
    record.version += 1
    session.commit()
    return render(record)


def receipt_view(
    session: Session, receipt: ImportReceiptRecord, store: ProjectImportStore
) -> dict[str, object]:
    current = store.current_title(session, receipt.project_id)
    if current is None or is_deleted_project_title(current):
        raise problem("IMPORT_PROJECT_DELETED", "The imported project is no longer available.", 410)
    return {"project_id": receipt.project_id, "first_chapter_id": receipt.first_chapter_id}


def commit(
    session: Session,
    preview_id: str,
    version: int,
    source_sha256: str,
    key: str,
    title: str,
    store: ProjectImportStore,
) -> dict[str, object]:
    valid_id(key)
    if is_reserved_project_title(title):
        raise problem("IMPORT_INVALID", "Invalid project title.")
    try:
        from aiwebnovel.project.values import ProjectTitle

        ProjectTitle(title)
    except DomainError:
        raise problem("IMPORT_INVALID", "Invalid project title.") from None
    digest = _digest(
        json.dumps(
            [preview_id, version, source_sha256, title], ensure_ascii=False, separators=(",", ":")
        )
    )
    session.execute(text("BEGIN IMMEDIATE"))
    old = session.get(ImportReceiptRecord, key)
    if old is not None:
        if old.request_sha256 != digest:
            raise problem("IMPORT_CONFLICT", "The idempotency key belongs to another request.", 409)
        return receipt_view(session, old, store)
    record = _read(session, preview_id)
    if record.version != version or record.source_sha256 != source_sha256 or version == 0:
        raise problem("IMPORT_CONFLICT", "The import preview has changed.", 409)
    if (
        session.scalar(
            select(ImportReceiptRecord).where(ImportReceiptRecord.preview_id == record.id)
        )
        is not None
    ):
        raise problem("IMPORT_CONFLICT", "This preview was already imported.", 409)
    validate_parts(record.source_text, record.chapters)
    try:
        project = create_initial_project(title, "")
        now = utc_now()
        volume = create_initial_volume(
            volume_id=VolumeId.new(),
            revision_id=VolumeRevisionId.new(),
            project_id=project.project.id,
            title=NovelStructureTitle("第一卷"),
            summary=NovelStructureSummary(""),
            position=NovelStructurePosition(1),
            now=now,
        )
        store.persist(session, project)
        volume_stable, volume_head, volume_revision = volume_aggregate_to_records(volume)
        for row in (
            volume_stable,
            volume_revision,
            volume_head,
        ):
            session.add(row)
            session.flush()
        first = None
        for position, part in enumerate(record.chapters, 1):
            chapter = create_initial_chapter(
                chapter_id=ChapterId.new(),
                revision_id=ChapterRevisionId.new(),
                project_id=project.project.id,
                volume=volume.volume,
                title=NovelStructureTitle(str(part["title"])),
                summary=NovelStructureSummary(""),
                position=NovelStructurePosition(position),
                now=now,
            )
            body = record.source_text[cast(int, part["body_start"]) : cast(int, part["end"])]
            chapter = replace(
                chapter,
                current_revision=replace(chapter.current_revision, content=ManuscriptContent(body)),
            )
            stable, head, revision = chapter_aggregate_to_records(chapter)
            for chapter_row in (stable, revision, head):
                session.add(chapter_row)
                session.flush()
            if first is None:
                first = str(chapter.chapter.id)
        assert first is not None
        result = ImportReceiptRecord(
            idempotency_key=key,
            request_sha256=digest,
            preview_id=record.id,
            project_id=str(project.project.id),
            first_chapter_id=first,
        )
        session.add(result)
        session.flush()
        response: dict[str, object] = {"project_id": result.project_id, "first_chapter_id": first}
        session.commit()
        return response
    except Exception:
        session.rollback()
        raise
