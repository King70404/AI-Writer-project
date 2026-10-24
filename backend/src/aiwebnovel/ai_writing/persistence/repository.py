"""One SQLite write transaction for every state transition, including author adoption."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.models import ContextManifest, ContextSource, GeneratedText
from aiwebnovel.ai_writing.application.workflow_models import (
    MAX_CANDIDATE_EDITS,
    CandidateEdit,
    CandidateEditInvalid,
    CandidateStatus,
    ContextPack,
    ModelSnapshot,
    RunStatus,
    WorkflowCandidate,
    WorkflowConflict,
    WorkflowNotFound,
    WorkflowRun,
)
from aiwebnovel.ai_writing.errors import AIContextChanged
from aiwebnovel.ai_writing.persistence.models import (
    AICandidateEditAdoptionRecord,
    AICandidateEditRecord,
    AIWorkflowCandidateRecord,
    AIWorkflowRunRecord,
)
from aiwebnovel.novel_structure.identifiers import ChapterId
from aiwebnovel.novel_structure.persistence.workflow_transaction import (
    adopt_workflow_content,
    load_workflow_chapter,
)
from aiwebnovel.project.persistence.models import ProjectRecord


def _edit(record: AICandidateEditRecord) -> CandidateEdit:
    created = (
        record.created_at if record.created_at.tzinfo else record.created_at.replace(tzinfo=UTC)
    )
    return CandidateEdit(
        edit_id=record.id,
        candidate_id=record.candidate_id,
        sequence=record.sequence,
        parent_edit_id=record.parent_edit_id,
        text=record.text,
        character_count=record.character_count,
        base_revision_id=record.base_revision_id,
        base_version=record.base_version,
        created_at=created.isoformat(),
    )


class SqlAlchemyWorkflowRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[Session]:
        with self._session_factory() as session:
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
    def _candidates(session: Session, run_id: str) -> list[AIWorkflowCandidateRecord]:
        return list(
            session.scalars(
                select(AIWorkflowCandidateRecord)
                .where(AIWorkflowCandidateRecord.run_id == run_id)
                .order_by(AIWorkflowCandidateRecord.sequence)
            )
        )

    @classmethod
    def _snapshot(cls, session: Session, record: AIWorkflowRunRecord) -> WorkflowRun:
        payload = dict(record.payload)
        payload.pop("in_flight", None)
        model_snapshot = payload.pop("model_snapshot", None)
        context = payload.pop("context")
        manifest = dict(context["manifest"])
        manifest["included_sources"] = tuple(manifest["included_sources"])
        manifest["omitted_sources"] = tuple(manifest["omitted_sources"])
        manifest["sources"] = tuple(
            ContextSource(
                **{**source, "references": tuple(tuple(ref) for ref in source["references"])}
            )
            for source in manifest.get("sources", ())
        )
        latest: dict[str, AICandidateEditRecord] = {}
        for edit in session.scalars(
            select(AICandidateEditRecord)
            .where(AICandidateEditRecord.run_id == record.id)
            .order_by(AICandidateEditRecord.candidate_id, AICandidateEditRecord.sequence)
        ):
            latest[edit.candidate_id] = edit
        adoptions: dict[str, str] = {
            str(candidate_id): str(edit_id)
            for candidate_id, edit_id in session.execute(
                select(
                    AICandidateEditAdoptionRecord.candidate_id,
                    AICandidateEditAdoptionRecord.edit_id,
                ).where(
                    AICandidateEditAdoptionRecord.candidate_id.in_(
                        select(AIWorkflowCandidateRecord.id).where(
                            AIWorkflowCandidateRecord.run_id == record.id
                        )
                    )
                )
            ).all()
        }
        candidates = tuple(
            WorkflowCandidate(
                candidate_id=c.id,
                sequence=c.sequence,
                text=c.text,
                model=c.model,
                character_count=c.character_count,
                status=cast(CandidateStatus, c.status),
                adopted_revision_id=c.adopted_revision_id,
                adopted_version=c.adopted_version,
                latest_edit=_edit(latest[c.id]) if c.id in latest else None,
                edit_count=latest[c.id].sequence if c.id in latest else 0,
                adopted_edit_id=adoptions.get(c.id),
            )
            for c in cls._candidates(session, record.id)
        )
        return WorkflowRun(
            **payload,
            status=cast(RunStatus, record.status),
            context=ContextPack(context["text"], context["sha256"], ContextManifest(**manifest)),
            candidates=candidates,
            model_snapshot=ModelSnapshot(**model_snapshot) if model_snapshot else None,
        )

    @staticmethod
    def _load(session: Session, chapter_id: str, run_id: str) -> AIWorkflowRunRecord:
        load_workflow_chapter(session, chapter_id)
        record = session.scalar(
            select(AIWorkflowRunRecord).where(
                AIWorkflowRunRecord.id == run_id,
                AIWorkflowRunRecord.chapter_id == ChapterId.parse(chapter_id),
                AIWorkflowRunRecord.project_id.in_(ProjectRecord.active_ids()),
            )
        )
        if record is None:
            raise WorkflowNotFound
        return record

    @staticmethod
    def _check_head(session: Session, record: AIWorkflowRunRecord) -> None:
        chapter = load_workflow_chapter(session, str(record.chapter_id))
        if (
            str(chapter.head.revision_id) != record.payload["current_revision_id"]
            or int(chapter.chapter.concurrency_version) != record.payload["current_version"]
        ):
            raise AIContextChanged

    @staticmethod
    def _budget_available(record: AIWorkflowRunRecord) -> bool:
        return bool(
            record.payload["generated_steps"] < record.payload["max_steps"]
            and record.payload["max_output_characters"] - record.payload["generated_characters"]
            >= 200
        )

    def create(self, run: WorkflowRun) -> WorkflowRun:
        with self._transaction(write=True) as session:
            chapter = load_workflow_chapter(session, run.chapter_id)
            payload = asdict(run)
            payload.pop("status")
            payload.pop("candidates")
            payload["in_flight"] = False
            record = AIWorkflowRunRecord(
                id=run.run_id,
                created_at=datetime.now(UTC),
                chapter_id=chapter.chapter.id,
                project_id=chapter.chapter.project_id,
                status="ready",
                payload=payload,
            )
            self._check_head(session, record)
            session.add(record)
            session.flush()
            return self._snapshot(session, record)

    def get(self, chapter_id: str, run_id: str) -> WorkflowRun:
        with self._transaction() as session:
            return self._snapshot(session, self._load(session, chapter_id, run_id))

    def list(self, chapter_id: str) -> tuple[WorkflowRun, ...]:
        with self._transaction() as session:
            load_workflow_chapter(session, chapter_id)
            records = session.scalars(
                select(AIWorkflowRunRecord)
                .where(
                    AIWorkflowRunRecord.chapter_id == ChapterId.parse(chapter_id),
                    AIWorkflowRunRecord.project_id.in_(ProjectRecord.active_ids()),
                )
                .order_by(AIWorkflowRunRecord.created_at.desc(), AIWorkflowRunRecord.id.desc())
            )
            return tuple(self._snapshot(session, record) for record in records)

    def claim(self, chapter_id: str, run_id: str) -> WorkflowRun:
        with self._transaction(write=True) as session:
            record = self._load(session, chapter_id, run_id)
            self._check_head(session, record)
            if (
                record.status != "ready"
                or record.payload.get("in_flight")
                or not self._budget_available(record)
                or any(c.status == "pending" for c in self._candidates(session, run_id))
            ):
                raise WorkflowConflict
            record.status = "generating"
            record.payload = {
                **record.payload,
                "in_flight": True,
                "generated_steps": record.payload["generated_steps"] + 1,
                "last_error": None,
            }
            return self._snapshot(session, record)

    def finish(
        self, chapter_id: str, run_id: str, generated: GeneratedText, character_count: int
    ) -> WorkflowRun:
        with self._transaction(write=True) as session:
            record = self._load(session, chapter_id, run_id)
            if not record.payload.get("in_flight"):
                raise WorkflowConflict
            self._check_head(session, record)
            record.payload = {
                **record.payload,
                "in_flight": False,
                "generated_characters": record.payload["generated_characters"] + character_count,
            }
            session.add(
                AIWorkflowCandidateRecord(
                    id=str(uuid4()),
                    run_id=run_id,
                    chapter_id=record.chapter_id,
                    sequence=record.payload["generated_steps"],
                    text=generated.text,
                    model=generated.model,
                    character_count=character_count,
                    status="pending",
                )
            )
            if record.status != "paused":
                record.status = "ready" if self._budget_available(record) else "completed"
            session.flush()
            return self._snapshot(session, record)

    def fail(self, chapter_id: str, run_id: str, error_code: str) -> None:
        with self._transaction(write=True) as session:
            # A deleted project must remain invisible even during provider error recovery.
            record = session.get(AIWorkflowRunRecord, run_id)
            if (
                record is not None
                and str(record.chapter_id) == chapter_id
                and record.payload.get("in_flight")
            ):
                record.status = "paused"
                record.payload = {**record.payload, "in_flight": False, "last_error": error_code}

    def transition(self, chapter_id: str, run_id: str, *, resume: bool) -> WorkflowRun:
        with self._transaction(write=True) as session:
            record = self._load(session, chapter_id, run_id)
            if resume:
                self._check_head(session, record)
                if (
                    record.status not in ("paused", "interrupted")
                    or record.payload.get("in_flight")
                    or not self._budget_available(record)
                ):
                    raise WorkflowConflict
                record.status = "ready"
                record.payload = {**record.payload, "last_error": None}
            elif record.status != "completed":
                record.status = "paused"
            return self._snapshot(session, record)

    @classmethod
    def _candidate(
        cls, session: Session, chapter_id: str, candidate_id: str
    ) -> tuple[AIWorkflowRunRecord, AIWorkflowCandidateRecord]:
        load_workflow_chapter(session, chapter_id)
        candidate = session.get(AIWorkflowCandidateRecord, candidate_id)
        if candidate is None or str(candidate.chapter_id) != chapter_id:
            raise WorkflowNotFound
        return cls._load(session, chapter_id, candidate.run_id), candidate

    @staticmethod
    def _latest_edit(session: Session, candidate_id: str) -> AICandidateEditRecord | None:
        return session.scalar(
            select(AICandidateEditRecord)
            .where(AICandidateEditRecord.candidate_id == candidate_id)
            .order_by(AICandidateEditRecord.sequence.desc())
            .limit(1)
        )

    def adopt(
        self,
        chapter_id: str,
        candidate_id: str,
        expected_version: int,
        idempotency_key: str,
        edit_id: str | None = None,
    ) -> WorkflowRun:
        with self._transaction(write=True) as session:
            record, candidate = self._candidate(session, chapter_id, candidate_id)
            # Receipt is checked before stale If-Match, so network retries never duplicate a revision.
            if candidate.status == "adopted":
                adopted_edit = session.get(AICandidateEditAdoptionRecord, candidate.id)
                if (
                    candidate.idempotency_key != idempotency_key
                    or (None if adopted_edit is None else adopted_edit.edit_id) != edit_id
                ):
                    raise WorkflowConflict
                return self._snapshot(session, record)
            used_key = session.scalar(
                select(AIWorkflowCandidateRecord.id).where(
                    AIWorkflowCandidateRecord.chapter_id == ChapterId.parse(chapter_id),
                    AIWorkflowCandidateRecord.idempotency_key == idempotency_key,
                )
            )
            if (
                candidate.status != "pending"
                or used_key is not None
                or record.payload.get("in_flight")
            ):
                raise WorkflowConflict
            self._check_head(session, record)
            chapter = load_workflow_chapter(session, chapter_id)
            text = candidate.text
            if edit_id is not None:
                edit = self._latest_edit(session, candidate.id)
                # Only the newest author edit may be adopted; an older one is stale.
                if edit is None or edit.id != edit_id:
                    raise WorkflowConflict
                if (
                    str(chapter.head.revision_id) != edit.base_revision_id
                    or int(chapter.chapter.concurrency_version) != edit.base_version
                ):
                    raise AIContextChanged
                text = edit.text
            content = str(chapter.current_revision.content)
            if record.payload["operation"] == "continue":
                content += ("\n\n" if content else "") + text
            else:
                encoded = content.encode("utf-16-le")
                start, end = (
                    record.payload["selection_start"] * 2,
                    record.payload["selection_end"] * 2,
                )
                if encoded[start:end].decode("utf-16-le") != record.payload["selected_text"]:
                    raise AIContextChanged
                content = (encoded[:start] + text.encode("utf-16-le") + encoded[end:]).decode(
                    "utf-16-le"
                )
            result = adopt_workflow_content(session, chapter, content, expected_version)
            if edit_id is not None:
                session.add(
                    AICandidateEditAdoptionRecord(
                        candidate_id=candidate.id, edit_id=edit_id, created_at=datetime.now(UTC)
                    )
                )
            candidate.status = "adopted"
            candidate.idempotency_key = idempotency_key
            candidate.adopted_revision_id = str(result.head.revision_id)
            candidate.adopted_version = int(result.chapter.concurrency_version)
            record.payload = {
                **record.payload,
                "current_revision_id": candidate.adopted_revision_id,
                "current_version": candidate.adopted_version,
            }
            session.flush()
            return self._snapshot(session, record)

    def create_edit(
        self, chapter_id: str, candidate_id: str, text: str, parent_edit_id: str | None
    ) -> WorkflowRun:
        with self._transaction(write=True) as session:
            record, candidate = self._candidate(session, chapter_id, candidate_id)
            if candidate.status != "pending" or record.payload.get("in_flight"):
                raise WorkflowConflict
            latest = self._latest_edit(session, candidate.id)
            # The parent is an optimistic version: a second window cannot silently fork.
            if (None if latest is None else latest.id) != parent_edit_id:
                raise WorkflowConflict
            sequence = 1 if latest is None else latest.sequence + 1
            if sequence > MAX_CANDIDATE_EDITS:
                raise CandidateEditInvalid
            if text == (candidate.text if latest is None else latest.text):
                raise CandidateEditInvalid
            chapter = load_workflow_chapter(session, chapter_id)
            session.add(
                AICandidateEditRecord(
                    id=str(uuid4()),
                    candidate_id=candidate.id,
                    run_id=record.id,
                    chapter_id=record.chapter_id,
                    project_id=record.project_id,
                    sequence=sequence,
                    parent_edit_id=parent_edit_id,
                    text=text,
                    character_count=sum(not character.isspace() for character in text),
                    base_revision_id=str(chapter.head.revision_id),
                    base_version=int(chapter.chapter.concurrency_version),
                    created_at=datetime.now(UTC),
                )
            )
            session.flush()
            return self._snapshot(session, record)

    def list_edits(self, chapter_id: str, candidate_id: str) -> tuple[CandidateEdit, ...]:
        with self._transaction() as session:
            self._candidate(session, chapter_id, candidate_id)
            return tuple(
                _edit(edit)
                for edit in session.scalars(
                    select(AICandidateEditRecord)
                    .where(AICandidateEditRecord.candidate_id == candidate_id)
                    .order_by(AICandidateEditRecord.sequence)
                )
            )

    def release_unsent(self, chapter_id: str, run_id: str, error_code: str) -> None:
        """Return a claimed step whose request was refused locally and never sent."""
        with self._transaction(write=True) as session:
            record = session.get(AIWorkflowRunRecord, run_id)
            if (
                record is not None
                and str(record.chapter_id) == chapter_id
                and record.payload.get("in_flight")
            ):
                if record.status == "generating":
                    record.status = "ready"
                record.payload = {
                    **record.payload,
                    "in_flight": False,
                    "generated_steps": max(0, record.payload["generated_steps"] - 1),
                    "last_error": error_code,
                }

    def discard(self, chapter_id: str, candidate_id: str) -> WorkflowRun:
        with self._transaction(write=True) as session:
            record, candidate = self._candidate(session, chapter_id, candidate_id)
            if candidate.status == "adopted" or record.payload.get("in_flight"):
                raise WorkflowConflict
            candidate.status = "discarded"
            session.flush()
            return self._snapshot(session, record)

    def recover_interrupted(self) -> None:
        with self._transaction(write=True) as session:
            for record in session.scalars(
                select(AIWorkflowRunRecord).where(
                    AIWorkflowRunRecord.status.in_(("generating", "paused"))
                )
            ):
                if record.status == "generating" or record.payload.get("in_flight"):
                    record.status = "interrupted"
                    record.payload = {
                        **record.payload,
                        "in_flight": False,
                        "last_error": "PROCESS_INTERRUPTED",
                    }
