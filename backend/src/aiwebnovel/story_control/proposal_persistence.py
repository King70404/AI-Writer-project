"""Plan proposal rows; every transition re-reads and writes under the SQLite writer lock."""

from collections.abc import Callable
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    literal_column,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from aiwebnovel.db.base import Base
from aiwebnovel.db.types import PrefixedUlidType
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_control.proposal_models import (
    PlanProposal,
    PlanProposalConflict,
    PlanProposalNotFound,
)


class PlanProposalRecord(Base):
    __tablename__ = "plan_proposals"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_plan_proposal_version"),
        Index("ix_plan_proposal_project", "project_id", "goal_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[ProjectId] = mapped_column(
        PrefixedUlidType(ProjectId), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    goal_id: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SqlAlchemyPlanProposalStore:
    def __init__(self, sessions: Callable[[], Session], projects: ProjectQueryService) -> None:
        self._sessions = sessions
        self._projects = projects

    def _active(self, project_id: str) -> ProjectId:
        identifier = ProjectId.parse(project_id)
        if self._projects.get_project(GetProjectQuery(project_id)) is None:
            raise ProjectNotFound(identifier)
        return identifier

    @staticmethod
    def _record(session: Session, project: ProjectId, proposal_id: str) -> PlanProposalRecord:
        record = session.scalar(
            select(PlanProposalRecord).where(
                PlanProposalRecord.id == proposal_id, PlanProposalRecord.project_id == project
            )
        )
        if record is None:
            raise PlanProposalNotFound
        return record

    def recover_interrupted(self) -> None:
        """A send interrupted by a restart is failed, never resent automatically."""
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            for record in session.scalars(
                select(PlanProposalRecord).where(
                    func.json_extract(PlanProposalRecord.payload, "$.status") == "running"
                )
            ):
                proposal = PlanProposal.model_validate(record.payload)
                record.payload = PlanProposal.model_validate(
                    {**proposal.model_dump(), "status": "failed", "error": "AIProviderInterrupted"}
                ).model_dump(mode="json")
                record.version += 1
            session.commit()

    def create(self, proposal: PlanProposal) -> tuple[PlanProposal, int]:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            project = self._active(proposal.project_id)
            session.add(
                PlanProposalRecord(
                    id=proposal.id,
                    project_id=project,
                    goal_id=proposal.goal_id,
                    version=1,
                    payload=proposal.model_dump(mode="json"),
                )
            )
            session.commit()
        return proposal, 1

    def get(self, project_id: str, proposal_id: str) -> tuple[PlanProposal, int]:
        project = self._active(project_id)
        with self._sessions() as session:
            record = self._record(session, project, proposal_id)
            return PlanProposal.model_validate(record.payload), record.version

    def list_recent(self, project_id: str, limit: int) -> tuple[tuple[PlanProposal, int], ...]:
        project = self._active(project_id)
        with self._sessions() as session:
            records = session.scalars(
                select(PlanProposalRecord)
                .where(PlanProposalRecord.project_id == project)
                .order_by(literal_column("plan_proposals.rowid").desc())
                .limit(limit)
            ).all()
            return tuple(
                (PlanProposal.model_validate(record.payload), record.version) for record in records
            )

    def count(self, project_id: str) -> int:
        project = self._active(project_id)
        with self._sessions() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(PlanProposalRecord)
                    .where(PlanProposalRecord.project_id == project)
                )
                or 0
            )

    def mutate(
        self,
        project_id: str,
        proposal_id: str,
        expected_version: int | None,
        transition: Callable[[PlanProposal], PlanProposal],
    ) -> tuple[PlanProposal, int]:
        with self._sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            project = self._active(project_id)
            record = self._record(session, project, proposal_id)
            if expected_version is not None and record.version != expected_version:
                raise PlanProposalConflict
            current = PlanProposal.model_validate(record.payload)
            updated = transition(current)
            if updated == current:
                return current, record.version
            record.payload = updated.model_dump(mode="json")
            record.version += 1
            version = record.version
            session.commit()
        return updated, version
