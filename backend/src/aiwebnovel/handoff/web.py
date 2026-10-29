"""External text handoff, explicit import and author adoption."""

import hashlib
import io
import json
import uuid
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.web import require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.handoff.persistence import ExternalCandidateRecord, HandoffRecord
from aiwebnovel.imports.web import import_session
from aiwebnovel.novel_structure.persistence.workflow_transaction import (
    adopt_workflow_content,
    load_workflow_chapter,
)
from aiwebnovel.novel_structure.values import ManuscriptContent
from aiwebnovel.novel_structure.web.dependencies import get_required_version


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    instruction: str = Field(max_length=4000)
    include_manuscript: bool
    context_sha256: str | None = None


class Adoption(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    idempotency_key: str


def fail(code: str, status: int = 409) -> AppError:
    return AppError(
        code=code, message="External handoff could not be completed.", status_code=status
    )


def build(session: Session, chapter_id: str, data: Input) -> dict[str, object]:
    chapter = load_workflow_chapter(session, chapter_id)
    prose = str(chapter.current_revision.content) if data.include_manuscript else ""
    context = json.dumps(
        {
            "instruction": data.instruction,
            "manuscript": prose,
            "base_revision": str(chapter.head.revision_id),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(context) > 60000:
        raise fail("HANDOFF_TOO_LARGE", 422)
    return {
        "handoff_id": None,
        "chapter_id": chapter_id,
        "base_version": int(chapter.chapter.concurrency_version),
        "base_revision": str(chapter.head.revision_id),
        "context": context,
        "context_sha256": hashlib.sha256(context.encode()).hexdigest(),
    }


def view(h: HandoffRecord, candidates: list[ExternalCandidateRecord]) -> dict[str, object]:
    return {
        "handoff_id": h.id,
        "chapter_id": h.chapter_id,
        "base_version": h.base_version,
        "context_sha256": h.context_sha256,
        "context": h.context,
        "candidates": [candidate(c, h.base_version) for c in candidates],
    }


def candidate(c: ExternalCandidateRecord, version: int) -> dict[str, object]:
    return {
        "candidate_id": c.id,
        "text": c.text,
        "status": "adopted" if c.adoption_key else "pending",
        "base_version": version,
    }


def router(api_prefix: str) -> APIRouter:
    r = APIRouter(prefix=api_prefix + "/chapters/{chapter_id}/handoffs", tags=["External handoffs"])
    SessionDep = Annotated[Session, Depends(import_session)]
    Json = Annotated[None, Depends(require_json)]

    @r.post("/preview")
    def preview(chapter_id: str, body: Input, s: SessionDep, _: Json) -> dict[str, object]:
        return build(s, chapter_id, body)

    @r.post("")
    def create(chapter_id: str, body: Input, s: SessionDep, _: Json) -> dict[str, object]:
        s.execute(text("BEGIN IMMEDIATE"))
        data = build(s, chapter_id, body)
        if body.context_sha256 is None or body.context_sha256 != data["context_sha256"]:
            raise fail("HANDOFF_CHANGED")
        h = HandoffRecord(
            id=str(uuid.uuid4()),
            chapter_id=chapter_id,
            base_version=data["base_version"],
            base_revision=data["base_revision"],
            context_sha256=data["context_sha256"],
            context=data["context"],
        )
        s.add(h)
        s.commit()
        return view(h, [])

    def get(s: Session, chapter_id: str, handoff_id: str) -> HandoffRecord:
        load_workflow_chapter(s, chapter_id)
        h = s.get(HandoffRecord, handoff_id)
        if h is None or h.chapter_id != chapter_id:
            raise fail("HANDOFF_NOT_FOUND", 404)
        return h

    @r.get("")
    def listing(chapter_id: str, s: SessionDep) -> list[dict[str, object]]:
        load_workflow_chapter(s, chapter_id)
        rows = s.scalars(
            select(HandoffRecord)
            .where(HandoffRecord.chapter_id == chapter_id)
            .order_by(HandoffRecord.id.desc())
            .limit(100)
        ).all()
        return [
            view(
                h,
                list(
                    s.scalars(
                        select(ExternalCandidateRecord).where(
                            ExternalCandidateRecord.handoff_id == h.id
                        )
                    ).all()
                ),
            )
            for h in rows
        ]

    @r.get("/{handoff_id}/download")
    def download(chapter_id: str, handoff_id: str, s: SessionDep) -> Response:
        h = get(s, chapter_id, handoff_id)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("task.md", "请依据 context.json 完成原创续写。\n")
            archive.writestr("context.json", h.context)
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {"format_version": 1, "handoff_id": h.id, "context_sha256": h.context_sha256},
                    ensure_ascii=False,
                ),
            )
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=handoff.zip",
                "Cache-Control": "no-store",
            },
        )

    @r.post("/{handoff_id}/candidates")
    async def add(
        chapter_id: str, handoff_id: str, request: Request, s: SessionDep
    ) -> dict[str, object]:
        raw = await request.body()
        if len(raw) > 262144:
            raise fail("HANDOFF_TOO_LARGE", 413)

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate")
                result[key] = value
            return result

        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
        except (UnicodeDecodeError, ValueError):
            raise fail("HANDOFF_INVALID", 422) from None
        h = get(s, chapter_id, handoff_id)
        if (
            not isinstance(data, dict)
            or set(data) != {"format_version", "handoff_id", "context_sha256", "text"}
            or type(data["format_version"]) is not int
            or data["format_version"] != 1
            or data["handoff_id"] != h.id
            or data["context_sha256"] != h.context_sha256
            or not isinstance(data["text"], str)
        ):
            raise fail("HANDOFF_INVALID", 422)
        value = data["text"]
        if not 200 <= len("".join(value.split())) <= 300:
            raise fail("HANDOFF_INVALID", 422)
        try:
            ManuscriptContent(value)
        except DomainError:
            raise fail("HANDOFF_INVALID", 422) from None
        digest = hashlib.sha256(value.encode()).hexdigest()
        c = s.scalar(
            select(ExternalCandidateRecord).where(
                ExternalCandidateRecord.handoff_id == h.id,
                ExternalCandidateRecord.text_sha256 == digest,
            )
        )
        if c is None:
            c = ExternalCandidateRecord(
                id=str(uuid.uuid4()), handoff_id=h.id, text=value, text_sha256=digest
            )
            s.add(c)
            s.commit()
        return candidate(c, h.base_version)

    @r.post("/{handoff_id}/candidates/{candidate_id}/adopt")
    def adopt(
        chapter_id: str,
        handoff_id: str,
        candidate_id: str,
        body: Adoption,
        s: SessionDep,
        _: Json,
        expected: Annotated[ConcurrencyVersion, Depends(get_required_version)],
    ) -> dict[str, object]:
        try:
            uuid.UUID(body.idempotency_key)
        except ValueError:
            raise fail("HANDOFF_INVALID", 422) from None
        s.execute(text("BEGIN IMMEDIATE"))
        h = get(s, chapter_id, handoff_id)
        c = s.get(ExternalCandidateRecord, candidate_id)
        if c is None or c.handoff_id != h.id:
            raise fail("HANDOFF_NOT_FOUND", 404)
        if c.adoption_key:
            if c.adoption_key != body.idempotency_key:
                raise fail("HANDOFF_CHANGED")
            return candidate(c, h.base_version)
        chapter = load_workflow_chapter(s, chapter_id)
        if str(chapter.head.revision_id) != h.base_revision or int(expected) != h.base_version:
            raise fail("HANDOFF_CHANGED")
        original = str(chapter.current_revision.content)
        adopt_workflow_content(
            s, chapter, original + ("\n\n" if original else "") + c.text, int(expected)
        )
        c.adoption_key = body.idempotency_key
        s.commit()
        return candidate(c, h.base_version)

    return r
