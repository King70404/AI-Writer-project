"""Transactional SQLAlchemy implementation of CharacterRepository."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Never, cast

from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import (
    IntegrityError,
    MultipleResultsFound,
    SQLAlchemyError,
    StatementError,
)
from sqlalchemy.orm import Session

from aiwebnovel.character.entities import CharacterAggregate
from aiwebnovel.character.errors import (
    CharacterAlreadyExists,
    CharacterDataCorruption,
    CharacterNotFound,
    CharacterProjectNotFound,
    CharacterRepositoryError,
    InvalidCharacterState,
)
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.persistence.mappers import (
    character_aggregate_from_records,
    character_aggregate_to_records,
    character_revision_to_record,
)
from aiwebnovel.character.persistence.queries import (
    character_compare_and_swap,
    character_head_compare_and_swap,
    character_identity_query,
    current_character_query,
    project_exists_query,
)
from aiwebnovel.character.repository import CharacterRepository
from aiwebnovel.character.transitions import append_character_revision
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.errors import ConcurrencyConflict, DomainError
from aiwebnovel.domain.time import Clock

SessionFactory = Callable[[], Session]


class _CharacterCasMiss(Exception):
    pass


class _CharacterHeadCasMiss(Exception):
    pass


class SqlAlchemyCharacterRepository(CharacterRepository):
    """Persist Character aggregates with one independent Session per call."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def create(self, aggregate: CharacterAggregate) -> CharacterAggregate:
        """Atomically persist stable identity, revision one, and its head."""
        self._validate_initial_aggregate(aggregate)
        session = self._new_session()
        try:
            self._begin_immediate(session)
            if session.scalar(project_exists_query(aggregate.character.project_id)) is None:
                raise CharacterProjectNotFound(aggregate.character.project_id)
            if session.scalar(character_identity_query(aggregate.character.id)) is not None:
                raise CharacterAlreadyExists(aggregate.character.id)

            character_record, head_record, revision_record = character_aggregate_to_records(
                aggregate
            )
            session.add(character_record)
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
            raise CharacterRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        finally:
            session.close()

    def get(self, character_id: CharacterId) -> CharacterAggregate | None:
        """Read one consistent current aggregate with one business query."""
        self._validate_character_id(character_id)
        session = self._new_session()
        try:
            aggregate = self._load_current(session, character_id)
            session.rollback()
            return aggregate
        except CharacterDataCorruption:
            session.rollback()
            raise
        except SQLAlchemyError as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        finally:
            session.close()

    def append_revision(
        self,
        character_id: CharacterId,
        *,
        expected_version: ConcurrencyVersion,
        name: CharacterName,
        role: CharacterRole,
        profile: CharacterProfile,
        clock: Clock,
        revision_id_factory: Callable[[], CharacterRevisionId],
    ) -> CharacterAggregate:
        """Append a complete revision and compare-and-swap stable object and head."""
        self._validate_append_input(
            character_id,
            expected_version,
            name,
            role,
            profile,
            clock,
            revision_id_factory,
        )
        session = self._new_session()
        cas_failure: Literal["character", "head"] | None = None
        try:
            self._begin_immediate(session)
            aggregate = self._load_current(session, character_id)
            if aggregate is None:
                raise CharacterNotFound(character_id)

            assert_expected_version(
                actual=aggregate.character.concurrency_version,
                expected=expected_version,
            )
            now = clock()
            revision_id = revision_id_factory()
            next_aggregate = append_character_revision(
                aggregate,
                expected_version=expected_version,
                revision_id=revision_id,
                name=name,
                role=role,
                profile=profile,
                now=now,
            )

            session.add(character_revision_to_record(next_aggregate.current_revision))
            session.flush()
            stable_result = cast(
                CursorResult[Any],
                session.execute(
                    character_compare_and_swap(
                        character_id,
                        expected_version,
                        next_aggregate.character.concurrency_version,
                        next_aggregate.character.updated_at,
                    )
                ),
            )
            if stable_result.rowcount != 1:
                raise _CharacterCasMiss

            head_result = cast(
                CursorResult[Any],
                session.execute(
                    character_head_compare_and_swap(
                        character_id,
                        aggregate.head.revision_id,
                        next_aggregate.head.revision_id,
                        next_aggregate.head.updated_at,
                    )
                ),
            )
            if head_result.rowcount != 1:
                raise _CharacterHeadCasMiss

            session.flush()
            session.commit()
            return next_aggregate
        except _CharacterCasMiss:
            cas_failure = "character"
            session.rollback()
        except _CharacterHeadCasMiss:
            cas_failure = "head"
            session.rollback()
        except DomainError:
            session.rollback()
            raise
        except (IntegrityError, SQLAlchemyError) as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        finally:
            session.close()

        if cas_failure == "character":
            self._raise_character_cas_failure(character_id, expected_version)
        assert cas_failure == "head"
        self._raise_head_cas_failure(character_id)

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise CharacterRepositoryError from exc

    @staticmethod
    def _begin_immediate(session: Session) -> None:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")

    @staticmethod
    def _validate_initial_aggregate(aggregate: CharacterAggregate) -> None:
        if (
            type(aggregate) is not CharacterAggregate
            or aggregate.character.concurrency_version.value != 1
            or aggregate.current_revision.revision_number.value != 1
        ):
            raise InvalidCharacterState

    @staticmethod
    def _validate_character_id(character_id: CharacterId) -> None:
        if type(character_id) is not CharacterId:
            raise InvalidCharacterState

    @staticmethod
    def _validate_append_input(
        character_id: CharacterId,
        expected_version: ConcurrencyVersion,
        name: CharacterName,
        role: CharacterRole,
        profile: CharacterProfile,
        clock: Clock,
        revision_id_factory: Callable[[], CharacterRevisionId],
    ) -> None:
        if (
            type(character_id) is not CharacterId
            or type(expected_version) is not ConcurrencyVersion
            or type(name) is not CharacterName
            or type(role) is not CharacterRole
            or type(profile) is not CharacterProfile
            or not callable(clock)
            or not callable(revision_id_factory)
        ):
            raise InvalidCharacterState

    @staticmethod
    def _load_current(
        session: Session,
        character_id: CharacterId,
    ) -> CharacterAggregate | None:
        try:
            row = session.execute(current_character_query(character_id)).one_or_none()
            if row is None:
                return None
            character_record, stored_project_id, head_record, revision_record = row
            if (
                stored_project_id is None
                or stored_project_id != character_record.project_id
                or head_record is None
                or revision_record is None
            ):
                raise CharacterDataCorruption
            return character_aggregate_from_records(
                character_record,
                head_record,
                revision_record,
            )
        except CharacterDataCorruption:
            raise
        except (
            DomainError,
            MultipleResultsFound,
            StatementError,
            TypeError,
            ValueError,
        ) as exc:
            raise CharacterDataCorruption from exc

    def _raise_character_cas_failure(
        self,
        character_id: CharacterId,
        expected_version: ConcurrencyVersion,
    ) -> Never:
        aggregate = self.get(character_id)
        if aggregate is None:
            raise CharacterNotFound(character_id)
        raise ConcurrencyConflict(
            expected_version=int(expected_version),
            actual_version=int(aggregate.character.concurrency_version),
        )

    def _raise_head_cas_failure(self, character_id: CharacterId) -> Never:
        if self.get(character_id) is None:
            raise CharacterNotFound(character_id)
        raise CharacterDataCorruption


__all__ = ["SqlAlchemyCharacterRepository"]
