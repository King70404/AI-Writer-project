"""Atomic claims and append-only versions with active-project ownership checks."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from aiwebnovel.ai_writing.application.models import GenerationMessage
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.writing_studio.application.models import (
    ReferenceAnalysis,
    ReferenceUnit,
    UnitAnalysis,
    WritingConflict,
    WritingNotFound,
    WritingReference,
    WritingRule,
    WritingRuleVersion,
)
from aiwebnovel.writing_studio.persistence.models import (
    WritingReferenceRecord,
    WritingRuleVersionRecord,
)


class SqlAlchemyWritingRepository:
    def __init__(
        self, session_factory: Callable[[], Session], projects: ProjectQueryService
    ) -> None:
        self._session_factory = session_factory
        self._projects = projects

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

    def _project(self, project_id: str) -> ProjectId:
        identifier = ProjectId.parse(project_id)
        # Writers already hold BEGIN IMMEDIATE, so a concurrent project deletion
        # cannot commit between this public query and our mutation.
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise WritingNotFound
        return identifier

    def _load(self, session: Session, project_id: str, reference_id: str) -> WritingReferenceRecord:
        identifier = self._project(project_id)
        record = session.scalar(
            select(WritingReferenceRecord).where(
                WritingReferenceRecord.id == reference_id,
                WritingReferenceRecord.project_id == identifier,
            )
        )
        if record is None:
            raise WritingNotFound
        return record

    @staticmethod
    def _reference(record: WritingReferenceRecord) -> WritingReference:
        payload = dict(record.payload)
        payload["model_snapshot"] = ModelSnapshot(**payload["model_snapshot"])
        payload["messages"] = tuple(GenerationMessage(**m) for m in payload["messages"])
        payload["units"] = tuple(ReferenceUnit(**unit) for unit in payload["units"])
        analysis = payload["analysis"]
        if analysis is not None:
            payload["analysis"] = ReferenceAnalysis(
                tuple(UnitAnalysis(**unit) for unit in analysis["units"]),
                analysis["long_form_notes"],
                tuple(WritingRule(**r) for r in analysis["rules"]),
            )
        return WritingReference(
            **payload,
            status=cast(Literal["ready", "analyzing", "analyzed", "failed"], record.status),
            version=record.version,
            attempts=record.attempts,
        )

    @staticmethod
    def _rules(record: WritingRuleVersionRecord) -> WritingRuleVersion:
        payload = dict(record.payload)
        payload["rules"] = tuple(WritingRule(**rule) for rule in payload["rules"])
        return WritingRuleVersion(**payload)

    def create_reference(self, reference: WritingReference) -> WritingReference:
        with self._transaction(write=True) as session:
            identifier = self._project(reference.project_id)
            payload = asdict(reference)
            for key in ("status", "version", "attempts"):
                payload.pop(key)
            record = WritingReferenceRecord(
                id=reference.id,
                project_id=identifier,
                status="ready",
                version=1,
                attempts=0,
                payload=payload,
            )
            session.add(record)
            return reference

    def get_reference(self, project_id: str, reference_id: str) -> WritingReference:
        with self._transaction() as session:
            return self._reference(self._load(session, project_id, reference_id))

    def list_references(self, project_id: str) -> tuple[WritingReference, ...]:
        with self._transaction() as session:
            identifier = self._project(project_id)
            records = session.scalars(
                select(WritingReferenceRecord)
                .where(WritingReferenceRecord.project_id == identifier)
                .order_by(WritingReferenceRecord.id)
            )
            return tuple(self._reference(record) for record in records)

    def claim(self, project_id: str, reference_id: str, version: int) -> WritingReference:
        with self._transaction(write=True) as session:
            record = self._load(session, project_id, reference_id)
            if (
                record.version != version
                or record.status not in ("ready", "failed")
                or record.attempts >= 3
            ):
                raise WritingConflict
            record.status = "analyzing"
            record.version += 1
            record.attempts += 1
            record.payload = {**record.payload, "last_error": None}
            return self._reference(record)

    def finish(
        self, project_id: str, reference_id: str, analysis: ReferenceAnalysis
    ) -> WritingReference:
        with self._transaction(write=True) as session:
            record = self._load(session, project_id, reference_id)
            if record.status != "analyzing":
                raise WritingConflict
            record.status = "analyzed"
            record.version += 1
            record.payload = {**record.payload, "analysis": asdict(analysis), "last_error": None}
            return self._reference(record)

    def fail(self, project_id: str, reference_id: str, error: str) -> None:
        with self._transaction(write=True) as session:
            record = self._load(session, project_id, reference_id)
            if record.status == "analyzing":
                record.status = "failed"
                record.version += 1
                record.payload = {**record.payload, "last_error": error}

    def recover_interrupted(self) -> None:
        with self._transaction(write=True) as session:
            for record in session.scalars(
                select(WritingReferenceRecord).where(
                    WritingReferenceRecord.status == "analyzing",
                )
            ):
                if self._projects.get_project(GetProjectQuery(str(record.project_id))) is None:
                    continue
                record.status = "failed"
                record.version += 1
                record.payload = {**record.payload, "last_error": "WritingAnalysisInterrupted"}

    def save_rules(
        self, rules: WritingRuleVersion, expected_version: int | None
    ) -> WritingRuleVersion:
        with self._transaction(write=True) as session:
            identifier = self._project(rules.project_id)
            if rules.reference_id is not None:
                source = self._load(session, rules.project_id, rules.reference_id)
                if source.status != "analyzed":
                    raise WritingConflict
            latest = session.scalar(
                select(WritingRuleVersionRecord)
                .where(
                    WritingRuleVersionRecord.rule_id == rules.rule_id,
                    WritingRuleVersionRecord.project_id == identifier,
                )
                .order_by(WritingRuleVersionRecord.version.desc())
                .limit(1)
            )
            if expected_version is not None:
                if latest is None:
                    raise WritingNotFound
                if latest.version != expected_version:
                    raise WritingConflict
            elif latest is not None:
                raise WritingConflict
            session.add(
                WritingRuleVersionRecord(
                    id=rules.id,
                    rule_id=rules.rule_id,
                    project_id=identifier,
                    version=rules.version,
                    reference_id=rules.reference_id,
                    payload=asdict(rules),
                )
            )
            return rules

    def list_rules(self, project_id: str) -> tuple[WritingRuleVersion, ...]:
        with self._transaction() as session:
            identifier = self._project(project_id)
            return tuple(
                self._rules(record)
                for record in session.scalars(
                    select(WritingRuleVersionRecord)
                    .where(WritingRuleVersionRecord.project_id == identifier)
                    .order_by(WritingRuleVersionRecord.rule_id, WritingRuleVersionRecord.version)
                )
            )

    def get_rules(
        self, project_id: str, version_ids: tuple[str, ...]
    ) -> tuple[WritingRuleVersion, ...]:
        with self._transaction() as session:
            identifier = self._project(project_id)
            records = {
                record.id: record
                for record in session.scalars(
                    select(WritingRuleVersionRecord).where(
                        WritingRuleVersionRecord.project_id == identifier,
                        WritingRuleVersionRecord.id.in_(version_ids),
                    )
                )
            }
            if len(records) != len(version_ids):
                raise WritingNotFound
            return tuple(self._rules(records[version_id]) for version_id in version_ids)
