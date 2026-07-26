"""SQLAlchemy adapter for immutable Project revision-history reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import Integer, Select, bindparam, select, text
from sqlalchemy.exc import SQLAlchemyError, StatementError
from sqlalchemy.orm import Session

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.application.models import (
    ProjectRevisionHistoryItem,
    ProjectRevisionHistoryPage,
    ProjectRevisionHistoryPosition,
    ProjectRevisionHistorySnapshot,
)
from aiwebnovel.project.application.queries import (
    validate_project_revision_history_limit,
)
from aiwebnovel.project.errors import (
    DomainError,
    ProjectDataCorruption,
    ProjectNotFound,
    ProjectRepositoryError,
)
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.mappers import project_aggregate_from_records
from aiwebnovel.project.persistence.models import ProjectRevisionRecord
from aiwebnovel.project.persistence.queries import current_project_query
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

SessionFactory = Callable[[], Session]
ProjectRevisionHistoryRow = tuple[object, object, object, object, object]
ProjectRevisionSnapshotRow = tuple[object, object, object, object, object, object]


@dataclass(frozen=True, slots=True)
class _ProjectHistoryState:
    project_id: ProjectId
    current_revision_id: ProjectRevisionId
    current_revision_number: RevisionNumber
    created_at: datetime
    updated_at: datetime


def project_revision_history_statement(
    *,
    project_id: ProjectId,
    limit: int,
    after: RevisionNumber | None,
) -> Select[ProjectRevisionHistoryRow]:
    """Build the fixed descending keyset query without loading descriptions."""
    statement = select(
        ProjectRevisionRecord.id,
        ProjectRevisionRecord.project_id,
        ProjectRevisionRecord.revision_number,
        ProjectRevisionRecord.title,
        ProjectRevisionRecord.created_at,
    ).where(ProjectRevisionRecord.project_id == project_id)
    if after is not None:
        statement = statement.where(ProjectRevisionRecord.revision_number < after)
    limit_clause = text("LIMIT :project_revision_history_limit").bindparams(
        bindparam(
            "project_revision_history_limit",
            value=limit + 1,
            type_=Integer(),
        )
    )
    return cast(
        Select[ProjectRevisionHistoryRow],
        statement.order_by(ProjectRevisionRecord.revision_number.desc()).suffix_with(limit_clause),
    )


def project_revision_statement(
    *,
    project_id: ProjectId,
    revision_number: RevisionNumber,
) -> Select[ProjectRevisionSnapshotRow]:
    """Build one exact immutable revision read scoped to its owning Project."""
    return cast(
        Select[ProjectRevisionSnapshotRow],
        select(
            ProjectRevisionRecord.id,
            ProjectRevisionRecord.project_id,
            ProjectRevisionRecord.revision_number,
            ProjectRevisionRecord.title,
            ProjectRevisionRecord.description,
            ProjectRevisionRecord.created_at,
        ).where(
            ProjectRevisionRecord.project_id == project_id,
            ProjectRevisionRecord.revision_number == revision_number,
        ),
    )


def _history_item_from_row(
    row: ProjectRevisionHistoryRow,
    *,
    state: _ProjectHistoryState,
) -> ProjectRevisionHistoryItem:
    revision_id, project_id, revision_number, title, created_at = row
    if (
        type(revision_id) is not ProjectRevisionId
        or type(project_id) is not ProjectId
        or type(revision_number) is not RevisionNumber
        or type(title) is not str
        or type(created_at) is not datetime
        or project_id != state.project_id
        or created_at < state.created_at
        or created_at > state.updated_at
    ):
        raise ProjectDataCorruption
    canonical_title = str(ProjectTitle(title))
    if canonical_title != title:
        raise ProjectDataCorruption
    return ProjectRevisionHistoryItem(
        revision_id=str(revision_id),
        revision_number=int(revision_number),
        title=canonical_title,
        created_at=created_at,
        is_current=revision_number == state.current_revision_number,
    )


def _history_snapshot_from_row(
    row: ProjectRevisionSnapshotRow,
    *,
    state: _ProjectHistoryState,
) -> ProjectRevisionHistorySnapshot:
    revision_id, project_id, revision_number, title, description, created_at = row
    if (
        type(revision_id) is not ProjectRevisionId
        or type(project_id) is not ProjectId
        or type(revision_number) is not RevisionNumber
        or type(title) is not str
        or type(description) is not str
        or type(created_at) is not datetime
        or project_id != state.project_id
        or created_at < state.created_at
        or created_at > state.updated_at
    ):
        raise ProjectDataCorruption
    canonical_title = str(ProjectTitle(title))
    canonical_description = str(ProjectDescription(description))
    if canonical_title != title or canonical_description != description:
        raise ProjectDataCorruption
    return ProjectRevisionHistorySnapshot(
        project_id=str(project_id),
        revision_id=str(revision_id),
        revision_number=int(revision_number),
        title=canonical_title,
        description=canonical_description,
        created_at=created_at,
        is_current=revision_number == state.current_revision_number,
        current_revision_number=int(state.current_revision_number),
    )


class SqlAlchemyProjectRevisionHistoryReader:
    """Read immutable Project revisions with one independent Session per call."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def list_page(
        self,
        *,
        project_id: ProjectId,
        limit: int,
        after: RevisionNumber | None,
    ) -> ProjectRevisionHistoryPage:
        """Return at most one validated descending keyset page."""
        self._validate_project_id(project_id)
        validated_limit = validate_project_revision_history_limit(limit)
        if after is not None and type(after) is not RevisionNumber:
            raise TypeError("after must be a RevisionNumber or None")
        session = self._new_session()
        try:
            state = self._load_state(session, project_id)
            rows = (
                session.execute(
                    project_revision_history_statement(
                        project_id=project_id,
                        limit=validated_limit,
                        after=after,
                    )
                )
                .tuples()
                .all()
            )
            mapped = tuple(_history_item_from_row(row, state=state) for row in rows)
            if not mapped and after is None:
                raise ProjectDataCorruption
            items = mapped[:validated_limit]
            has_more = len(mapped) > validated_limit
            page = ProjectRevisionHistoryPage(
                project_id=str(project_id),
                current_revision_number=int(state.current_revision_number),
                items=items,
                next_position=(
                    ProjectRevisionHistoryPosition(
                        project_id=str(project_id),
                        revision_number=items[-1].revision_number,
                    )
                    if has_more
                    else None
                ),
                has_more=has_more,
            )
            session.rollback()
            return page
        except (ProjectNotFound, ProjectDataCorruption):
            session.rollback()
            raise
        except (DomainError, TypeError, ValueError) as exc:
            session.rollback()
            raise ProjectDataCorruption from exc
        except StatementError as exc:
            session.rollback()
            if isinstance(exc.orig, (DomainError, TypeError, ValueError)):
                raise ProjectDataCorruption from exc
            raise ProjectRepositoryError from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        finally:
            session.close()

    def get_revision(
        self,
        *,
        project_id: ProjectId,
        revision_number: RevisionNumber,
    ) -> ProjectRevisionHistorySnapshot | None:
        """Return one exact immutable revision after validating current state."""
        self._validate_project_id(project_id)
        if type(revision_number) is not RevisionNumber:
            raise TypeError("revision_number must be a RevisionNumber")
        session = self._new_session()
        try:
            state = self._load_state(session, project_id)
            row = (
                session.execute(
                    project_revision_statement(
                        project_id=project_id,
                        revision_number=revision_number,
                    )
                )
                .tuples()
                .one_or_none()
            )
            snapshot = None if row is None else _history_snapshot_from_row(row, state=state)
            session.rollback()
            return snapshot
        except (ProjectNotFound, ProjectDataCorruption):
            session.rollback()
            raise
        except (DomainError, TypeError, ValueError) as exc:
            session.rollback()
            raise ProjectDataCorruption from exc
        except StatementError as exc:
            session.rollback()
            if isinstance(exc.orig, (DomainError, TypeError, ValueError)):
                raise ProjectDataCorruption from exc
            raise ProjectRepositoryError from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        finally:
            session.close()

    @staticmethod
    def _validate_project_id(project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise TypeError("project_id must be a ProjectId")

    @staticmethod
    def _load_state(session: Session, project_id: ProjectId) -> _ProjectHistoryState:
        try:
            row = session.execute(current_project_query(project_id)).one_or_none()
            if row is None:
                raise ProjectNotFound(project_id)
            project_record, head_record, revision_record = row
            if head_record is None or revision_record is None:
                raise ProjectDataCorruption
            aggregate = project_aggregate_from_records(
                project_record,
                head_record,
                revision_record,
            )
            if (
                type(aggregate.project.concurrency_version) is not ConcurrencyVersion
                or str(aggregate.current_revision.title) != revision_record.title
                or str(aggregate.current_revision.description) != revision_record.description
                or aggregate.current_revision.created_at < aggregate.project.created_at
                or aggregate.current_revision.created_at > aggregate.project.updated_at
            ):
                raise ProjectDataCorruption
            return _ProjectHistoryState(
                project_id=aggregate.project.id,
                current_revision_id=aggregate.current_revision.id,
                current_revision_number=aggregate.current_revision.revision_number,
                created_at=aggregate.project.created_at,
                updated_at=aggregate.project.updated_at,
            )
        except (ProjectNotFound, ProjectDataCorruption):
            raise
        except (DomainError, TypeError, ValueError) as exc:
            raise ProjectDataCorruption from exc

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise ProjectRepositoryError from exc


__all__ = [
    "SqlAlchemyProjectRevisionHistoryReader",
    "project_revision_history_statement",
    "project_revision_statement",
]
