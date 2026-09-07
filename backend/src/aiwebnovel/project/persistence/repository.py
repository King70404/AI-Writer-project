"""Transactional SQLAlchemy implementation of the Project repository contract."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Never, cast

from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from aiwebnovel.project import (
    Clock,
    ConcurrencyConflict,
    ConcurrencyVersion,
    assert_expected_version,
)
from aiwebnovel.project.deletion import is_deleted_project_title
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.errors import (
    DomainError,
    InvalidProjectState,
    ProjectAlreadyExists,
    ProjectDataCorruption,
    ProjectNotFound,
    ProjectPersistenceConflict,
    ProjectRepositoryError,
)
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.mappers import (
    project_aggregate_from_records,
    project_aggregate_to_records,
    project_revision_to_record,
)
from aiwebnovel.project.persistence.queries import (
    current_project_query,
    head_compare_and_swap,
    project_compare_and_swap,
)
from aiwebnovel.project.repository import ProjectRepository
from aiwebnovel.project.transitions import create_next_project_revision
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

SessionFactory = Callable[[], Session]


class _ProjectCasMiss(Exception):
    pass


class _HeadCasMiss(Exception):
    pass


class SqlAlchemyProjectRepository(ProjectRepository):
    """Persist one Project aggregate per independent synchronous Session."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def create(self, aggregate: ProjectAggregate) -> ProjectAggregate:
        """Persist all three aggregate rows in one immediate SQLite transaction."""
        if type(aggregate) is not ProjectAggregate:
            raise InvalidProjectState

        session = self._new_session()
        try:
            self._begin_immediate(session)
            if self._load_current(session, aggregate.project.id) is not None:
                raise ProjectAlreadyExists(aggregate.project.id)

            project_record, head_record, revision_record = project_aggregate_to_records(aggregate)
            session.add(project_record)
            session.flush()
            session.add(revision_record)
            session.flush()
            session.add(head_record)
            session.flush()
            session.commit()
            return aggregate
        except DomainError:
            session.rollback()
            raise
        except IntegrityError as exc:
            session.rollback()
            raise ProjectPersistenceConflict from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        finally:
            session.close()

    def get(self, project_id: ProjectId) -> ProjectAggregate | None:
        """Restore one active aggregate; tombstoned Projects behave as absent."""
        self._validate_project_id(project_id)
        session = self._new_session()
        try:
            aggregate = self._load_current(session, project_id)
            session.rollback()
            if aggregate is not None and is_deleted_project_title(
                str(aggregate.current_revision.title)
            ):
                return None
            return aggregate
        except ProjectDataCorruption:
            session.rollback()
            raise
        except SQLAlchemyError as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        finally:
            session.close()

    def append_revision(
        self,
        project_id: ProjectId,
        expected_version: ConcurrencyVersion,
        title: ProjectTitle,
        description: ProjectDescription,
        *,
        clock: Clock | None = None,
        revision_id_factory: Callable[[], ProjectRevisionId] = ProjectRevisionId.new,
    ) -> ProjectAggregate:
        """Append a revision, then compare-and-swap Project and Head atomically."""
        self._validate_append_input(project_id, expected_version, title, description)
        session = self._new_session()
        cas_failure: Literal["project", "head"] | None = None
        try:
            self._begin_immediate(session)
            aggregate = self._load_current(session, project_id)
            if aggregate is None or is_deleted_project_title(
                str(aggregate.current_revision.title)
            ):
                raise ProjectNotFound(project_id)

            assert_expected_version(
                actual=aggregate.project.concurrency_version,
                expected=expected_version,
            )
            next_aggregate = create_next_project_revision(
                aggregate,
                expected_version,
                str(title),
                str(description),
                clock=clock,
                revision_id_factory=revision_id_factory,
            )

            session.add(project_revision_to_record(next_aggregate.current_revision))
            session.flush()
            project_result = cast(
                CursorResult[Any],
                session.execute(
                    project_compare_and_swap(
                        project_id,
                        expected_version,
                        next_aggregate.project.concurrency_version,
                        next_aggregate.project.updated_at,
                    )
                ),
            )
            if project_result.rowcount != 1:
                raise _ProjectCasMiss

            head_result = cast(
                CursorResult[Any],
                session.execute(
                    head_compare_and_swap(
                        project_id,
                        aggregate.head.revision_id,
                        next_aggregate.head.revision_id,
                        next_aggregate.head.updated_at,
                    )
                ),
            )
            if head_result.rowcount != 1:
                raise _HeadCasMiss

            session.flush()
            session.commit()
            return next_aggregate
        except _ProjectCasMiss:
            cas_failure = "project"
            session.rollback()
        except _HeadCasMiss:
            cas_failure = "head"
            session.rollback()
        except DomainError:
            session.rollback()
            raise
        except IntegrityError as exc:
            session.rollback()
            raise ProjectPersistenceConflict from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise ProjectRepositoryError from exc
        finally:
            session.close()

        if cas_failure == "project":
            self._raise_project_cas_failure(project_id, expected_version)
        assert cas_failure == "head"
        self._raise_head_cas_failure(project_id)

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise ProjectRepositoryError from exc

    @staticmethod
    def _begin_immediate(session: Session) -> None:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    @staticmethod
    def _validate_project_id(project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise InvalidProjectState

    @staticmethod
    def _validate_append_input(
        project_id: ProjectId,
        expected_version: ConcurrencyVersion,
        title: ProjectTitle,
        description: ProjectDescription,
    ) -> None:
        if (
            type(project_id) is not ProjectId
            or type(expected_version) is not ConcurrencyVersion
            or type(title) is not ProjectTitle
            or type(description) is not ProjectDescription
        ):
            raise InvalidProjectState

    @staticmethod
    def _load_current(session: Session, project_id: ProjectId) -> ProjectAggregate | None:
        try:
            row = session.execute(current_project_query(project_id)).one_or_none()
            if row is None:
                return None
            project_record, head_record, revision_record = row
            if head_record is None or revision_record is None:
                raise ProjectDataCorruption
            return project_aggregate_from_records(
                project_record,
                head_record,
                revision_record,
            )
        except ProjectDataCorruption:
            raise
        except (DomainError, TypeError, ValueError) as exc:
            raise ProjectDataCorruption from exc

    def _raise_project_cas_failure(
        self,
        project_id: ProjectId,
        expected_version: ConcurrencyVersion,
    ) -> Never:
        aggregate = self.get(project_id)
        if aggregate is None:
            raise ProjectNotFound(project_id)
        raise ConcurrencyConflict(
            expected_version=int(expected_version),
            actual_version=int(aggregate.project.concurrency_version),
        )

    def _raise_head_cas_failure(self, project_id: ProjectId) -> Never:
        if self.get(project_id) is None:
            raise ProjectNotFound(project_id)
        raise ProjectPersistenceConflict


__all__ = ["SqlAlchemyProjectRepository"]
