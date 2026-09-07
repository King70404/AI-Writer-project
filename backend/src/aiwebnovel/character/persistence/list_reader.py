"""Read-only SQLAlchemy adapter for stable Character keyset pages."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import cast

from sqlalchemy import Integer, Select, and_, bindparam, or_, select, text
from sqlalchemy.exc import SQLAlchemyError, StatementError
from sqlalchemy.orm import Session

from aiwebnovel.character.application.models import (
    CharacterListItem,
    CharacterListPage,
    CharacterListPosition,
)
from aiwebnovel.character.application.queries import validate_character_list_limit
from aiwebnovel.character.errors import (
    CharacterDataCorruption,
    CharacterProjectNotFound,
    CharacterRepositoryError,
    InvalidCharacterState,
)
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.persistence.models import (
    CharacterHeadRecord,
    CharacterRecord,
    CharacterRevisionRecord,
)
from aiwebnovel.character.values import CharacterName, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord

SessionFactory = Callable[[], Session]
CharacterListRow = tuple[
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
    object,
]


def character_list_statement(
    project_id: ProjectId,
    *,
    limit: int,
    after: CharacterListPosition | None,
) -> Select[CharacterListRow]:
    statement = (
        select(
            CharacterRecord.id,
            CharacterRecord.project_id,
            CharacterRecord.concurrency_version,
            CharacterRecord.created_at,
            CharacterRecord.updated_at,
            CharacterHeadRecord.character_id,
            CharacterHeadRecord.revision_id,
            CharacterHeadRecord.updated_at,
            CharacterRevisionRecord.id,
            CharacterRevisionRecord.character_id,
            CharacterRevisionRecord.revision_number,
            CharacterRevisionRecord.name,
            CharacterRevisionRecord.role,
            CharacterRevisionRecord.created_at,
        )
        .outerjoin(
            CharacterHeadRecord,
            CharacterHeadRecord.character_id == CharacterRecord.id,
        )
        .outerjoin(
            CharacterRevisionRecord,
            and_(
                CharacterRevisionRecord.character_id == CharacterHeadRecord.character_id,
                CharacterRevisionRecord.id == CharacterHeadRecord.revision_id,
            ),
        )
        .where(CharacterRecord.project_id == project_id)
    )
    if after is not None:
        statement = statement.where(
            or_(
                CharacterRecord.created_at < after.created_at,
                and_(
                    CharacterRecord.created_at == after.created_at,
                    CharacterRecord.id < after.character_id,
                ),
            )
        )
    limit_clause = text("LIMIT :character_list_limit").bindparams(
        bindparam("character_list_limit", value=limit + 1, type_=Integer())
    )
    statement = statement.order_by(
        CharacterRecord.created_at.desc(),
        CharacterRecord.id.desc(),
    ).suffix_with(limit_clause)
    return cast(Select[CharacterListRow], statement)


def _list_item_from_row(
    row: CharacterListRow,
    *,
    project_id: ProjectId,
) -> CharacterListItem:
    (
        character_id,
        stored_project_id,
        concurrency_version,
        character_created_at,
        character_updated_at,
        head_character_id,
        head_revision_id,
        head_updated_at,
        revision_id,
        revision_character_id,
        revision_number,
        name,
        role,
        revision_created_at,
    ) = row
    if (
        type(character_id) is not CharacterId
        or type(stored_project_id) is not ProjectId
        or type(concurrency_version) is not ConcurrencyVersion
        or type(character_created_at) is not datetime
        or type(character_updated_at) is not datetime
        or type(head_character_id) is not CharacterId
        or type(head_revision_id) is not CharacterRevisionId
        or type(head_updated_at) is not datetime
        or type(revision_id) is not CharacterRevisionId
        or type(revision_character_id) is not CharacterId
        or type(revision_number) is not RevisionNumber
        or type(name) is not str
        or type(role) is not str
        or type(revision_created_at) is not datetime
    ):
        raise CharacterDataCorruption
    if (
        stored_project_id != project_id
        or head_character_id != character_id
        or revision_character_id != character_id
        or head_revision_id != revision_id
        or concurrency_version.value != revision_number.value
        or character_created_at > character_updated_at
        or revision_created_at < character_created_at
        or character_updated_at != revision_created_at
        or character_updated_at != head_updated_at
    ):
        raise CharacterDataCorruption
    canonical_name = str(CharacterName(name))
    canonical_role = str(CharacterRole(role))
    if canonical_name != name or canonical_role != role:
        raise CharacterDataCorruption
    return CharacterListItem(
        character_id=str(character_id),
        current_revision_id=str(revision_id),
        revision_number=int(revision_number),
        concurrency_version=int(concurrency_version),
        name=canonical_name,
        role=canonical_role,
        created_at=character_created_at,
        updated_at=character_updated_at,
    )


class SqlAlchemyCharacterListReader:
    """Read one Character page with one independent read-only Session."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def list_for_project(
        self,
        project_id: ProjectId,
        *,
        limit: int,
        after: CharacterListPosition | None,
    ) -> CharacterListPage:
        if type(project_id) is not ProjectId:
            raise InvalidCharacterState
        validated_limit = validate_character_list_limit(limit)
        if after is not None and type(after) is not CharacterListPosition:
            raise TypeError("after must be a CharacterListPosition or None")
        if after is not None and after.project_id != project_id:
            raise ValueError("after position must belong to the requested Project")
        session = self._new_session()
        try:
            if (
                session.scalar(ProjectRecord.active_ids().where(ProjectRecord.id == project_id))
                is None
            ):
                raise CharacterProjectNotFound(project_id)
            rows = (
                session.execute(
                    character_list_statement(
                        project_id,
                        limit=validated_limit,
                        after=after,
                    )
                )
                .tuples()
                .all()
            )
            items = tuple(
                _list_item_from_row(row, project_id=project_id) for row in rows[:validated_limit]
            )
            has_more = len(rows) > validated_limit
            next_position = (
                CharacterListPosition(
                    project_id=project_id,
                    created_at=items[-1].created_at,
                    character_id=CharacterId.parse(items[-1].character_id),
                )
                if has_more
                else None
            )
            page = CharacterListPage(
                project_id=str(project_id),
                items=items,
                next_position=next_position,
                has_more=has_more,
            )
            session.rollback()
            return page
        except (CharacterProjectNotFound, CharacterDataCorruption):
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

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise CharacterRepositoryError from exc


__all__ = ["SqlAlchemyCharacterListReader", "character_list_statement"]
