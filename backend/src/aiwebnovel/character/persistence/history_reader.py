"""SQLAlchemy adapter for immutable Character revision-history reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import Integer, Select, and_, bindparam, select, text
from sqlalchemy.exc import SQLAlchemyError, StatementError
from sqlalchemy.orm import Session

from aiwebnovel.character.application.history_models import (
    CharacterRevisionHistoryItem,
    CharacterRevisionHistoryPage,
    CharacterRevisionHistoryPosition,
    CharacterRevisionSnapshot,
)
from aiwebnovel.character.application.history_queries import (
    validate_character_revision_history_limit,
)
from aiwebnovel.character.errors import (
    CharacterDataCorruption,
    CharacterNotFound,
    CharacterRepositoryError,
)
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.persistence.models import (
    CharacterHeadRecord,
    CharacterRecord,
    CharacterRevisionRecord,
)
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord

SessionFactory = Callable[[], Session]
CharacterHistoryStateRow = tuple[
    object,
    object,
    object,
    object,
    object,
    object,
    object,
    object,
    object,
    object,
    object,
    object,
    object,
]
CharacterRevisionHistoryRow = tuple[object, object, object, object, object]
CharacterRevisionSnapshotRow = tuple[object, object, object, object, object, object]


@dataclass(frozen=True, slots=True)
class _CharacterHistoryState:
    character_id: CharacterId
    project_id: ProjectId
    current_revision_id: CharacterRevisionId
    current_revision_number: RevisionNumber
    created_at: datetime
    updated_at: datetime


def character_history_state_statement(
    character_id: CharacterId,
) -> Select[CharacterHistoryStateRow]:
    """Read stable, Project, Head, and current Revision state without profile."""
    return cast(
        Select[CharacterHistoryStateRow],
        select(
            CharacterRecord.id,
            CharacterRecord.project_id,
            CharacterRecord.concurrency_version,
            CharacterRecord.created_at,
            CharacterRecord.updated_at,
            ProjectRecord.id,
            CharacterHeadRecord.character_id,
            CharacterHeadRecord.revision_id,
            CharacterHeadRecord.updated_at,
            CharacterRevisionRecord.id,
            CharacterRevisionRecord.character_id,
            CharacterRevisionRecord.revision_number,
            CharacterRevisionRecord.created_at,
        )
        .outerjoin(ProjectRecord, ProjectRecord.id == CharacterRecord.project_id)
        .outerjoin(CharacterHeadRecord, CharacterHeadRecord.character_id == CharacterRecord.id)
        .outerjoin(
            CharacterRevisionRecord,
            and_(
                CharacterRevisionRecord.character_id == CharacterHeadRecord.character_id,
                CharacterRevisionRecord.id == CharacterHeadRecord.revision_id,
            ),
        )
        .where(CharacterRecord.id == character_id),
    )


def character_revision_history_statement(
    *, character_id: CharacterId, limit: int, after: RevisionNumber | None
) -> Select[CharacterRevisionHistoryRow]:
    """Build the fixed descending keyset query without loading profile."""
    statement = select(
        CharacterRevisionRecord.id,
        CharacterRevisionRecord.revision_number,
        CharacterRevisionRecord.name,
        CharacterRevisionRecord.role,
        CharacterRevisionRecord.created_at,
    ).where(CharacterRevisionRecord.character_id == character_id)
    if after is not None:
        statement = statement.where(CharacterRevisionRecord.revision_number < after)
    limit_clause = text("LIMIT :character_revision_history_limit").bindparams(
        bindparam(
            "character_revision_history_limit",
            value=limit + 1,
            type_=Integer(),
        )
    )
    return cast(
        Select[CharacterRevisionHistoryRow],
        statement.order_by(CharacterRevisionRecord.revision_number.desc()).suffix_with(
            limit_clause
        ),
    )


def character_revision_statement(
    *, character_id: CharacterId, revision_number: RevisionNumber
) -> Select[CharacterRevisionSnapshotRow]:
    """Build one exact immutable revision read scoped to its Character."""
    return cast(
        Select[CharacterRevisionSnapshotRow],
        select(
            CharacterRevisionRecord.id,
            CharacterRevisionRecord.revision_number,
            CharacterRevisionRecord.name,
            CharacterRevisionRecord.role,
            CharacterRevisionRecord.profile,
            CharacterRevisionRecord.created_at,
        ).where(
            CharacterRevisionRecord.character_id == character_id,
            CharacterRevisionRecord.revision_number == revision_number,
        ),
    )


def _require_utc_time(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise CharacterDataCorruption
    return value


def _state_from_row(row: CharacterHistoryStateRow) -> _CharacterHistoryState:
    (
        character_id,
        project_id,
        concurrency_version,
        created_value,
        updated_value,
        existing_project_id,
        head_character_id,
        head_revision_id,
        head_updated_value,
        revision_id,
        revision_character_id,
        revision_number,
        revision_created_value,
    ) = row
    created_at = _require_utc_time(created_value)
    updated_at = _require_utc_time(updated_value)
    head_updated_at = _require_utc_time(head_updated_value)
    revision_created_at = _require_utc_time(revision_created_value)
    if (
        type(character_id) is not CharacterId
        or type(project_id) is not ProjectId
        or type(existing_project_id) is not ProjectId
        or type(concurrency_version) is not ConcurrencyVersion
        or type(head_character_id) is not CharacterId
        or type(head_revision_id) is not CharacterRevisionId
        or type(revision_id) is not CharacterRevisionId
        or type(revision_character_id) is not CharacterId
        or project_id != existing_project_id
        or head_character_id != character_id
        or revision_character_id != character_id
        or head_revision_id != revision_id
        or type(revision_number) is not RevisionNumber
        or int(concurrency_version) != int(revision_number)
        or created_at > updated_at
        or updated_at != head_updated_at
        or updated_at != revision_created_at
    ):
        raise CharacterDataCorruption
    return _CharacterHistoryState(
        character_id=character_id,
        project_id=project_id,
        current_revision_id=revision_id,
        current_revision_number=revision_number,
        created_at=created_at,
        updated_at=updated_at,
    )


def _canonical_text(name: object, role: object) -> tuple[str, str]:
    if type(name) is not str or type(role) is not str:
        raise CharacterDataCorruption
    canonical_name = str(CharacterName(name))
    canonical_role = str(CharacterRole(role))
    if canonical_name != name or canonical_role != role:
        raise CharacterDataCorruption
    return canonical_name, canonical_role


def _history_item_from_row(
    row: CharacterRevisionHistoryRow, *, state: _CharacterHistoryState
) -> CharacterRevisionHistoryItem:
    revision_id, revision_number, name, role, created_value = row
    created_at = _require_utc_time(created_value)
    if (
        type(revision_id) is not CharacterRevisionId
        or type(revision_number) is not RevisionNumber
        or created_at < state.created_at
    ):
        raise CharacterDataCorruption
    canonical_name, canonical_role = _canonical_text(name, role)
    return CharacterRevisionHistoryItem(
        revision_id=str(revision_id),
        revision_number=int(revision_number),
        name=canonical_name,
        role=canonical_role,
        created_at=created_at,
        is_current=revision_id == state.current_revision_id,
    )


def _snapshot_from_row(
    row: CharacterRevisionSnapshotRow, *, state: _CharacterHistoryState
) -> CharacterRevisionSnapshot:
    revision_id, revision_number, name, role, profile, created_value = row
    created_at = _require_utc_time(created_value)
    if (
        type(revision_id) is not CharacterRevisionId
        or type(revision_number) is not RevisionNumber
        or type(profile) is not str
        or created_at < state.created_at
    ):
        raise CharacterDataCorruption
    canonical_name, canonical_role = _canonical_text(name, role)
    canonical_profile = str(CharacterProfile(profile))
    if canonical_profile != profile:
        raise CharacterDataCorruption
    return CharacterRevisionSnapshot(
        character_id=str(state.character_id),
        project_id=str(state.project_id),
        revision_id=str(revision_id),
        revision_number=int(revision_number),
        name=canonical_name,
        role=canonical_role,
        profile=canonical_profile,
        created_at=created_at,
        is_current=revision_id == state.current_revision_id,
        current_revision_number=int(state.current_revision_number),
    )


class SqlAlchemyCharacterRevisionHistoryReader:
    """Read immutable Character revisions with an independent Session per call."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def list_revisions(
        self,
        character_id: CharacterId,
        *,
        limit: int,
        after: CharacterRevisionHistoryPosition | None,
    ) -> CharacterRevisionHistoryPage:
        self._validate_character_id(character_id)
        validated_limit = validate_character_revision_history_limit(limit)
        if after is not None:
            if type(after) is not CharacterRevisionHistoryPosition:
                raise TypeError("after must be a CharacterRevisionHistoryPosition or None")
            if after.character_id != character_id:
                raise ValueError("after must belong to the requested Character")
        session = self._new_session()
        try:
            state = self._load_state(session, character_id)
            rows = (
                session.execute(
                    character_revision_history_statement(
                        character_id=character_id,
                        limit=validated_limit,
                        after=after.revision_number if after is not None else None,
                    )
                )
                .tuples()
                .all()
            )
            mapped = tuple(_history_item_from_row(row, state=state) for row in rows)
            if not mapped and after is None:
                raise CharacterDataCorruption
            items = mapped[:validated_limit]
            has_more = len(mapped) > validated_limit
            page = CharacterRevisionHistoryPage(
                character_id=str(character_id),
                project_id=str(state.project_id),
                current_revision_number=int(state.current_revision_number),
                items=items,
                next_position=(
                    CharacterRevisionHistoryPosition(
                        character_id=character_id,
                        revision_number=RevisionNumber(items[-1].revision_number),
                    )
                    if has_more
                    else None
                ),
                has_more=has_more,
            )
            session.rollback()
            return page
        except (CharacterNotFound, CharacterDataCorruption):
            session.rollback()
            raise
        except (DomainError, TypeError, ValueError) as exc:
            session.rollback()
            raise CharacterDataCorruption from exc
        except StatementError as exc:
            session.rollback()
            if isinstance(exc.orig, (DomainError, TypeError, ValueError)):
                raise CharacterDataCorruption from exc
            raise CharacterRepositoryError from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        finally:
            session.close()

    def get_revision(
        self, character_id: CharacterId, revision_number: RevisionNumber
    ) -> CharacterRevisionSnapshot | None:
        self._validate_character_id(character_id)
        if type(revision_number) is not RevisionNumber:
            raise TypeError("revision_number must be a RevisionNumber")
        session = self._new_session()
        try:
            state = self._load_state(session, character_id)
            row = (
                session.execute(
                    character_revision_statement(
                        character_id=character_id,
                        revision_number=revision_number,
                    )
                )
                .tuples()
                .one_or_none()
            )
            snapshot = None if row is None else _snapshot_from_row(row, state=state)
            session.rollback()
            return snapshot
        except (CharacterNotFound, CharacterDataCorruption):
            session.rollback()
            raise
        except (DomainError, TypeError, ValueError) as exc:
            session.rollback()
            raise CharacterDataCorruption from exc
        except StatementError as exc:
            session.rollback()
            if isinstance(exc.orig, (DomainError, TypeError, ValueError)):
                raise CharacterDataCorruption from exc
            raise CharacterRepositoryError from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise CharacterRepositoryError from exc
        finally:
            session.close()

    @staticmethod
    def _validate_character_id(character_id: CharacterId) -> None:
        if type(character_id) is not CharacterId:
            raise TypeError("character_id must be a CharacterId")

    @staticmethod
    def _load_state(session: Session, character_id: CharacterId) -> _CharacterHistoryState:
        try:
            row = (
                session.execute(character_history_state_statement(character_id))
                .tuples()
                .one_or_none()
            )
            if row is None:
                raise CharacterNotFound(character_id)
            return _state_from_row(row)
        except (CharacterNotFound, CharacterDataCorruption):
            raise
        except (DomainError, TypeError, ValueError) as exc:
            raise CharacterDataCorruption from exc

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise CharacterRepositoryError from exc


__all__ = [
    "SqlAlchemyCharacterRevisionHistoryReader",
    "character_history_state_statement",
    "character_revision_history_statement",
    "character_revision_statement",
]
