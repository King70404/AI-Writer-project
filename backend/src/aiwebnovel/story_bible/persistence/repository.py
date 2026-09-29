"""Transactional SQLAlchemy implementation of StoryBibleRepository."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Never, cast

from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, MultipleResultsFound, SQLAlchemyError, StatementError
from sqlalchemy.orm import Session

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.errors import ConcurrencyConflict, DomainError
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord
from aiwebnovel.story_bible.entities import StoryBibleAggregate
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleState,
    StoryBibleAlreadyExists,
    StoryBibleDataCorruption,
    StoryBibleForProjectAlreadyExists,
    StoryBibleNotFound,
    StoryBibleProjectNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.mappers import (
    story_bible_aggregate_from_records,
    story_bible_aggregate_to_records,
    story_bible_revision_to_record,
)
from aiwebnovel.story_bible.persistence.models import StoryBibleRecord
from aiwebnovel.story_bible.persistence.queries import (
    current_story_bible_query,
    story_bible_compare_and_swap,
    story_bible_for_project_identity_query,
    story_bible_for_project_query,
    story_bible_head_compare_and_swap,
    story_bible_identity_query,
)
from aiwebnovel.story_bible.repository import StoryBibleRepository
from aiwebnovel.story_bible.transitions import append_story_bible_revision
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

SessionFactory = Callable[[], Session]


class _StoryBibleCasMiss(Exception):
    pass


class _StoryBibleHeadCasMiss(Exception):
    pass


class SqlAlchemyStoryBibleRepository(StoryBibleRepository):
    """Persist Story Bible aggregates with one independent Session per call."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def create(self, aggregate: StoryBibleAggregate) -> StoryBibleAggregate:
        self._validate_initial_aggregate(aggregate)
        session = self._new_session()
        try:
            self._begin_immediate(session)
            if (
                session.scalar(
                    ProjectRecord.active_ids().where(
                        ProjectRecord.id == aggregate.story_bible.project_id
                    )
                )
                is None
            ):
                raise StoryBibleProjectNotFound(aggregate.story_bible.project_id)
            if session.scalar(story_bible_identity_query(aggregate.story_bible.id)) is not None:
                raise StoryBibleAlreadyExists(aggregate.story_bible.id)
            if (
                session.scalar(
                    story_bible_for_project_identity_query(
                        aggregate.story_bible.project_id,
                    )
                )
                is not None
            ):
                raise StoryBibleForProjectAlreadyExists(
                    aggregate.story_bible.project_id,
                )

            story_bible_record, head_record, revision_record = story_bible_aggregate_to_records(
                aggregate
            )
            session.add(story_bible_record)
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
        except (IntegrityError, SQLAlchemyError) as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        finally:
            session.close()

    def get(self, story_bible_id: StoryBibleId) -> StoryBibleAggregate | None:
        self._validate_story_bible_id(story_bible_id)
        session = self._new_session()
        try:
            aggregate = self._load_current(session, story_bible_id, active_only=True)
            session.rollback()
            return aggregate
        except StoryBibleDataCorruption:
            session.rollback()
            raise
        except SQLAlchemyError as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        finally:
            session.close()

    def get_for_project(self, project_id: ProjectId) -> StoryBibleAggregate | None:
        self._validate_project_id(project_id)
        session = self._new_session()
        try:
            aggregate = self._load_for_project(session, project_id)
            session.rollback()
            return aggregate
        except (StoryBibleProjectNotFound, StoryBibleDataCorruption):
            session.rollback()
            raise
        except SQLAlchemyError as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        finally:
            session.close()

    def append_revision(
        self,
        story_bible_id: StoryBibleId,
        *,
        expected_version: ConcurrencyVersion,
        title: StoryBibleTitle,
        content: StoryBibleContent,
        clock: Clock,
        revision_id_factory: Callable[[], StoryBibleRevisionId],
    ) -> StoryBibleAggregate:
        self._validate_append_input(
            story_bible_id,
            expected_version,
            title,
            content,
            clock,
            revision_id_factory,
        )
        session = self._new_session()
        cas_failure: Literal["story_bible", "head"] | None = None
        try:
            self._begin_immediate(session)
            aggregate = self._load_current(session, story_bible_id)
            if aggregate is None:
                raise StoryBibleNotFound(story_bible_id)
            if (
                session.scalar(
                    ProjectRecord.active_ids().where(
                        ProjectRecord.id == aggregate.story_bible.project_id
                    )
                )
                is None
            ):
                raise StoryBibleProjectNotFound(aggregate.story_bible.project_id)

            assert_expected_version(
                actual=aggregate.story_bible.concurrency_version,
                expected=expected_version,
            )
            now = clock()
            revision_id = revision_id_factory()
            next_aggregate = append_story_bible_revision(
                aggregate,
                expected_version=expected_version,
                revision_id=revision_id,
                title=title,
                content=content,
                now=now,
            )

            session.add(story_bible_revision_to_record(next_aggregate.current_revision))
            session.flush()
            stable_result = cast(
                CursorResult[Any],
                session.execute(
                    story_bible_compare_and_swap(
                        story_bible_id,
                        expected_version,
                        next_aggregate.story_bible.concurrency_version,
                        next_aggregate.story_bible.updated_at,
                    )
                ),
            )
            if stable_result.rowcount != 1:
                raise _StoryBibleCasMiss

            head_result = cast(
                CursorResult[Any],
                session.execute(
                    story_bible_head_compare_and_swap(
                        story_bible_id,
                        aggregate.head.revision_id,
                        next_aggregate.head.revision_id,
                        next_aggregate.head.updated_at,
                    )
                ),
            )
            if head_result.rowcount != 1:
                raise _StoryBibleHeadCasMiss

            session.flush()
            session.commit()
            return next_aggregate
        except _StoryBibleCasMiss:
            cas_failure = "story_bible"
            session.rollback()
        except _StoryBibleHeadCasMiss:
            cas_failure = "head"
            session.rollback()
        except DomainError:
            session.rollback()
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        finally:
            session.close()

        if cas_failure == "story_bible":
            self._raise_story_bible_cas_failure(story_bible_id, expected_version)
        assert cas_failure == "head"
        self._raise_head_cas_failure(story_bible_id)

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise StoryBibleRepositoryError from exc

    @staticmethod
    def _begin_immediate(session: Session) -> None:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    @staticmethod
    def _validate_initial_aggregate(aggregate: StoryBibleAggregate) -> None:
        if (
            type(aggregate) is not StoryBibleAggregate
            or aggregate.story_bible.concurrency_version.value != 1
            or aggregate.current_revision.revision_number.value != 1
        ):
            raise InvalidStoryBibleState

    @staticmethod
    def _validate_story_bible_id(story_bible_id: StoryBibleId) -> None:
        if type(story_bible_id) is not StoryBibleId:
            raise InvalidStoryBibleState

    @staticmethod
    def _validate_project_id(project_id: ProjectId) -> None:
        if type(project_id) is not ProjectId:
            raise InvalidStoryBibleState

    @staticmethod
    def _validate_append_input(
        story_bible_id: StoryBibleId,
        expected_version: ConcurrencyVersion,
        title: StoryBibleTitle,
        content: StoryBibleContent,
        clock: Clock,
        revision_id_factory: Callable[[], StoryBibleRevisionId],
    ) -> None:
        if (
            type(story_bible_id) is not StoryBibleId
            or type(expected_version) is not ConcurrencyVersion
            or type(title) is not StoryBibleTitle
            or type(content) is not StoryBibleContent
            or not callable(clock)
            or not callable(revision_id_factory)
        ):
            raise InvalidStoryBibleState

    @staticmethod
    def _load_current(
        session: Session,
        story_bible_id: StoryBibleId,
        *,
        active_only: bool = False,
    ) -> StoryBibleAggregate | None:
        try:
            statement = current_story_bible_query(story_bible_id)
            if active_only:
                statement = statement.where(
                    StoryBibleRecord.project_id.not_in(ProjectRecord.deleted_ids())
                )
            row = session.execute(statement).one_or_none()
            if row is None:
                return None
            story_bible_record, head_record, revision_record = row
            if head_record is None or revision_record is None:
                raise StoryBibleDataCorruption
            return story_bible_aggregate_from_records(
                story_bible_record,
                head_record,
                revision_record,
            )
        except StoryBibleDataCorruption:
            raise
        except (DomainError, MultipleResultsFound, StatementError, TypeError, ValueError) as exc:
            raise StoryBibleDataCorruption from exc

    @staticmethod
    def _load_for_project(
        session: Session,
        project_id: ProjectId,
    ) -> StoryBibleAggregate | None:
        try:
            row = session.execute(
                story_bible_for_project_query(project_id).where(
                    ProjectRecord.id.in_(ProjectRecord.active_ids()),
                ),
            ).one_or_none()
            if row is None:
                raise StoryBibleProjectNotFound(project_id)
            stored_project_id, story_bible_record, head_record, revision_record = row
            if stored_project_id != project_id:
                raise StoryBibleDataCorruption
            if story_bible_record is None:
                return None
            if head_record is None or revision_record is None:
                raise StoryBibleDataCorruption
            return story_bible_aggregate_from_records(
                story_bible_record,
                head_record,
                revision_record,
            )
        except (StoryBibleProjectNotFound, StoryBibleDataCorruption):
            raise
        except (DomainError, MultipleResultsFound, StatementError, TypeError, ValueError) as exc:
            raise StoryBibleDataCorruption from exc

    def _raise_story_bible_cas_failure(
        self,
        story_bible_id: StoryBibleId,
        expected_version: ConcurrencyVersion,
    ) -> Never:
        aggregate = self.get(story_bible_id)
        if aggregate is None:
            raise StoryBibleNotFound(story_bible_id)
        raise ConcurrencyConflict(
            expected_version=int(expected_version),
            actual_version=int(aggregate.story_bible.concurrency_version),
        )

    def _raise_head_cas_failure(self, story_bible_id: StoryBibleId) -> Never:
        if self.get(story_bible_id) is None:
            raise StoryBibleNotFound(story_bible_id)
        raise StoryBibleDataCorruption


__all__ = ["SqlAlchemyStoryBibleRepository"]
