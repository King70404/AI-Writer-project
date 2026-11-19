"""Chapter draft rows. Every transition, adoption included, is one ``BEGIN IMMEDIATE`` write."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.ai_writing.chapter_draft_models import (
    MAX_DRAFTS_PER_CHAPTER,
    SEGMENT_MAX_CHARACTERS,
    SEGMENT_MIN_CHARACTERS,
    ChapterDraft,
    ChapterDraftConflict,
    ChapterDraftInvalid,
    ChapterDraftNotFound,
    ChapterDraftQuotaExhausted,
    ChapterDraftStale,
    DraftFailure,
    DraftReceipt,
    DraftSegment,
    DraftStatus,
    SegmentAction,
    segment_text,
)
from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.novel_structure.entities import ChapterAggregate
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.novel_structure.persistence.workflow_transaction import (
    adopt_workflow_content,
    load_workflow_chapter,
)
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord


class ChapterDraftRecord(Base):
    __tablename__ = "chapter_drafts"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_chapter_draft_version"),
        Index("ix_chapter_draft_chapter", "chapter_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    chapter_id: Mapped[ChapterId] = mapped_column(
        PrefixedUlidType(ChapterId), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def remaining(draft: ChapterDraft) -> tuple[int, int]:
    """Requests and generated characters still allowed by the draft's own quota."""
    return (
        draft.max_segments - draft.attempts,
        draft.max_output_characters - draft.generated_characters,
    )


def step_upper(draft: ChapterDraft) -> int:
    return min(SEGMENT_MAX_CHARACTERS, remaining(draft)[1])


def has_quota(draft: ChapterDraft) -> bool:
    requests, _ = remaining(draft)
    return requests > 0 and step_upper(draft) >= SEGMENT_MIN_CHARACTERS


def _changed(draft: ChapterDraft, **changes: object) -> ChapterDraft:
    return ChapterDraft.model_validate({**draft.model_dump(), **changes, "updated_at": _now()})


def _check_head(chapter: ChapterAggregate, draft: ChapterDraft) -> None:
    if (
        str(chapter.head.revision_id) != draft.current_revision_id
        or int(chapter.chapter.concurrency_version) != draft.current_version
    ):
        raise ChapterDraftStale


class SqlAlchemyChapterDraftStore:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._sessions = session_factory

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[Session]:
        with self._sessions() as session:
            try:
                if write:
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                yield session
                if write:
                    session.commit()
            except BaseException:
                session.rollback()
                raise

    @staticmethod
    def _record(session: Session, chapter_id: str, draft_id: str) -> ChapterDraftRecord:
        load_workflow_chapter(session, chapter_id)
        record = session.scalar(
            select(ChapterDraftRecord).where(
                ChapterDraftRecord.id == draft_id,
                ChapterDraftRecord.chapter_id == ChapterId.parse(chapter_id),
                ChapterDraftRecord.project_id.in_(ProjectRecord.active_ids()),
            )
        )
        if record is None:
            raise ChapterDraftNotFound
        return record

    @staticmethod
    def _write(record: ChapterDraftRecord, draft: ChapterDraft) -> tuple[ChapterDraft, int]:
        record.payload = draft.model_dump(mode="json")
        record.version += 1
        return draft, record.version

    # ------------------------------------------------------------------ reads

    def get(self, chapter_id: str, draft_id: str) -> tuple[ChapterDraft, int]:
        with self._transaction() as session:
            record = self._record(session, chapter_id, draft_id)
            return ChapterDraft.model_validate(record.payload), record.version

    def list_recent(self, chapter_id: str, limit: int) -> tuple[tuple[ChapterDraft, int], ...]:
        with self._transaction() as session:
            load_workflow_chapter(session, chapter_id)
            records = session.scalars(
                select(ChapterDraftRecord)
                .where(
                    ChapterDraftRecord.chapter_id == ChapterId.parse(chapter_id),
                    ChapterDraftRecord.project_id.in_(ProjectRecord.active_ids()),
                )
                .order_by(ChapterDraftRecord.created_at.desc(), ChapterDraftRecord.id.desc())
                .limit(limit)
            ).all()
            return tuple(
                (ChapterDraft.model_validate(record.payload), record.version) for record in records
            )

    # ------------------------------------------------------------------ preparation

    def create(self, draft: ChapterDraft) -> tuple[ChapterDraft, int]:
        with self._transaction(write=True) as session:
            chapter = load_workflow_chapter(session, draft.chapter_id)
            _check_head(chapter, draft)
            count = session.scalar(
                select(func.count())
                .select_from(ChapterDraftRecord)
                .where(ChapterDraftRecord.chapter_id == chapter.chapter.id)
            )
            if int(count or 0) >= MAX_DRAFTS_PER_CHAPTER:
                raise ChapterDraftInvalid
            project_id = str(chapter.chapter.project_id)
            draft = _changed(draft, project_id=project_id)
            if draft.writing_job_id is not None:
                self._bind_job(session, draft)
            session.add(
                ChapterDraftRecord(
                    id=draft.id,
                    project_id=chapter.chapter.project_id,
                    chapter_id=chapter.chapter.id,
                    created_at=draft.created_at,
                    version=1,
                    payload=draft.model_dump(mode="json"),
                )
            )
            return draft, 1

    @staticmethod
    def _bind_job(session: Session, draft: ChapterDraft) -> None:
        """Bind the draft as the job's current step, exactly like a bound workflow run."""
        from aiwebnovel.writing_jobs.persistence import WritingJobRecord, WritingJobRunRecord

        job = session.get(WritingJobRecord, draft.writing_job_id)
        if (
            job is None
            or job.project_id != draft.project_id
            or job.status != "planned"
            or job.current_index >= len(job.chapter_ids)
            or job.chapter_ids[job.current_index] != draft.chapter_id
            or session.scalar(
                select(WritingJobRunRecord.run_id)
                .where(
                    WritingJobRunRecord.job_id == job.id,
                    WritingJobRunRecord.step_index == job.current_index,
                )
                .limit(1)
            )
            is not None
        ):
            raise ChapterDraftConflict
        session.add(
            WritingJobRunRecord(
                run_id=draft.id, job_id=job.id, step_index=job.current_index, reserved_characters=0
            )
        )
        job.version += 1

    # ------------------------------------------------------------------ sending

    def claim(
        self, chapter_id: str, draft_id: str, expected_version: int | None
    ) -> tuple[ChapterDraft, int, DraftStatus]:
        """Reserve one request (and the job quota when bound) before anything is sent."""
        from aiwebnovel.writing_jobs.transaction import claim as claim_job

        with self._transaction(write=True) as session:
            record = self._record(session, chapter_id, draft_id)
            if expected_version is not None and record.version != expected_version:
                raise ChapterDraftConflict
            draft = ChapterDraft.model_validate(record.payload)
            if draft.status not in ("ready", "failed"):
                raise ChapterDraftConflict
            if not has_quota(draft):
                raise ChapterDraftQuotaExhausted
            # The draft continues a known revision; a hand edit stops the old dependency.
            _check_head(load_workflow_chapter(session, chapter_id), draft)
            claim_job(session, draft.id, step_upper(draft))
            previous = draft.status
            claimed, version = self._write(
                record,
                _changed(draft, status="running", attempts=draft.attempts + 1, last_error=None),
            )
            return claimed, version, previous

    def finish(self, chapter_id: str, draft_id: str, segment: DraftSegment) -> ChapterDraft:
        from aiwebnovel.writing_jobs.transaction import settle

        with self._transaction(write=True) as session:
            record = self._record(session, chapter_id, draft_id)
            draft = ChapterDraft.model_validate(record.payload)
            if draft.status != "running":
                raise ChapterDraftConflict
            settle(session, draft.id, segment.characters)
            updated = _changed(
                draft,
                segments=[*draft.segments, segment],
                generated_characters=draft.generated_characters + segment.characters,
            )
            updated = _changed(updated, status="ready" if has_quota(updated) else "exhausted")
            return self._write(record, updated)[0]

    def fail(self, chapter_id: str, draft_id: str, failure: DraftFailure) -> ChapterDraft:
        """Stop the draft; the request may have been billed, so its quota stays used."""
        from aiwebnovel.writing_jobs.transaction import settle

        with self._transaction(write=True) as session:
            record = self._record(session, chapter_id, draft_id)
            draft = ChapterDraft.model_validate(record.payload)
            settle(session, draft.id, None)
            updated = _changed(
                draft,
                status="failed",
                failures=[*draft.failures, failure],
                last_error=failure.error,
            )
            return self._write(record, updated)[0]

    def release_unsent(
        self, chapter_id: str, draft_id: str, previous: DraftStatus, error: str
    ) -> ChapterDraft:
        """Refused locally before sending: the request is returned, nothing was charged."""
        from aiwebnovel.writing_jobs.transaction import settle

        with self._transaction(write=True) as session:
            record = self._record(session, chapter_id, draft_id)
            draft = ChapterDraft.model_validate(record.payload)
            settle(session, draft.id, None, unsent=True)
            updated = _changed(
                draft, status=previous, attempts=draft.attempts - 1, last_error=error
            )
            return self._write(record, updated)[0]

    def recover_interrupted(self) -> None:
        """A send interrupted by a restart is failed, never resent automatically."""
        from aiwebnovel.writing_jobs.transaction import settle

        with self._transaction(write=True) as session:
            for record in session.scalars(
                select(ChapterDraftRecord).where(
                    func.json_extract(ChapterDraftRecord.payload, "$.status") == "running"
                )
            ):
                draft = ChapterDraft.model_validate(record.payload)
                settle(session, draft.id, None)
                failure = DraftFailure(
                    attempt=max(1, draft.attempts), error="AIProviderInterrupted", at=_now()
                )
                self._write(
                    record,
                    _changed(
                        draft,
                        status="failed",
                        failures=[*draft.failures, failure],
                        last_error=failure.error,
                    ),
                )

    # ------------------------------------------------------------------ adoption

    def adopt(
        self,
        chapter_id: str,
        draft_id: str,
        segment_indexes: list[int] | None,
        idempotency_key: str,
    ) -> tuple[ChapterDraft, int]:
        with self._transaction(write=True) as session:
            record = self._record(session, chapter_id, draft_id)
            draft = ChapterDraft.model_validate(record.payload)
            # The receipt is checked first, so a network retry never appends twice.
            receipt = next(
                (item for item in draft.receipts if item.idempotency_key == idempotency_key),
                None,
            )
            if receipt is not None:
                if segment_indexes is not None and segment_indexes != receipt.segment_indexes:
                    raise ChapterDraftConflict
                return draft, record.version
            if draft.status == "running":
                raise ChapterDraftConflict
            pending = [item.index for item in draft.segments if item.status == "pending"]
            chosen = pending if segment_indexes is None else segment_indexes
            if (
                not chosen
                or chosen != sorted(set(chosen))
                or any(index not in pending for index in chosen)
            ):
                raise ChapterDraftInvalid
            chapter = load_workflow_chapter(session, chapter_id)
            # A hand edit since the draft's revision refuses adoption; the draft is kept.
            _check_head(chapter, draft)
            # The author's edit is adopted instead of the model's original text.
            texts = [segment_text(draft.segments[index]) for index in chosen]
            content = str(chapter.current_revision.content)
            content += ("\n\n" if content else "") + "\n\n".join(texts)
            result = adopt_workflow_content(session, chapter, content, draft.current_version)
            revision_id = str(result.head.revision_id)
            version = int(result.chapter.concurrency_version)
            segments = [
                item.model_copy(update={"status": "adopted", "adopted_revision_id": revision_id})
                if item.index in chosen
                else item
                for item in draft.segments
            ]
            updated = _changed(
                draft,
                segments=[item.model_dump() for item in segments],
                receipts=[
                    *(item.model_dump() for item in draft.receipts),
                    DraftReceipt(
                        idempotency_key=idempotency_key,
                        segment_indexes=chosen,
                        revision_id=revision_id,
                        version=version,
                        adopted_at=_now(),
                    ).model_dump(),
                ],
                current_revision_id=revision_id,
                current_version=version,
            )
            return self._write(record, updated)

    # ------------------------------------------------------------------ author changes

    def change_segment(
        self,
        chapter_id: str,
        draft_id: str,
        index: int,
        expected_version: int,
        action: SegmentAction,
        text: str | None,
    ) -> tuple[ChapterDraft, int]:
        """Edit, discard or restore one segment; quota already used is never returned."""
        with self._transaction(write=True) as session:
            record = self._record(session, chapter_id, draft_id)
            if record.version != expected_version:
                raise ChapterDraftConflict
            draft = ChapterDraft.model_validate(record.payload)
            if draft.status == "running":
                raise ChapterDraftConflict
            if not 0 <= index < len(draft.segments):
                raise ChapterDraftInvalid
            segment = draft.segments[index]
            required = "discarded" if action == "restore" else "pending"
            if segment.status != required:
                raise ChapterDraftInvalid
            now = _now()
            if action == "discard":
                changed = segment.model_copy(update={"status": "discarded", "discarded_at": now})
            elif action == "restore":
                changed = segment.model_copy(update={"status": "pending", "discarded_at": None})
            elif text is None or text == segment.text:
                # Editing back to the model's original text removes the edit.
                changed = segment.model_copy(
                    update={"edited_text": None, "edited_characters": None, "edited_at": None}
                )
            else:
                changed = segment.model_copy(
                    update={
                        "edited_text": text,
                        "edited_characters": sum(not c.isspace() for c in text),
                        "edited_at": now,
                    }
                )
            segments = [changed if item.index == index else item for item in draft.segments]
            return self._write(
                record, _changed(draft, segments=[item.model_dump() for item in segments])
            )
