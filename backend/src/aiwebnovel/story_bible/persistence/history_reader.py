"""SQLAlchemy adapter for immutable Story Bible revision-history reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import Integer, Select, and_, bindparam, select, text
from sqlalchemy.exc import SQLAlchemyError, StatementError
from sqlalchemy.orm import Session

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.persistence.models import ProjectRecord
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryItem,
    StoryBibleRevisionHistoryPage,
    StoryBibleRevisionHistoryPosition,
    StoryBibleRevisionSnapshot,
)
from aiwebnovel.story_bible.application.history_queries import (
    validate_story_bible_revision_history_limit,
)
from aiwebnovel.story_bible.errors import (
    StoryBibleDataCorruption,
    StoryBibleNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.models import (
    StoryBibleHeadRecord,
    StoryBibleRecord,
    StoryBibleRevisionRecord,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

SessionFactory = Callable[[], Session]
StoryBibleHistoryStateRow = tuple[
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
StoryBibleRevisionHistoryRow = tuple[object, object, object, object]
StoryBibleRevisionSnapshotRow = tuple[object, object, object, object, object]


@dataclass(frozen=True, slots=True)
class _StoryBibleHistoryState:
    story_bible_id: StoryBibleId
    project_id: ProjectId
    current_revision_id: StoryBibleRevisionId
    current_revision_number: RevisionNumber
    created_at: datetime
    updated_at: datetime


def story_bible_history_state_statement(
    story_bible_id: StoryBibleId,
) -> Select[StoryBibleHistoryStateRow]:
    """Read stable, Project, Head, and current Revision state without content."""
    return cast(
        Select[StoryBibleHistoryStateRow],
        select(
            StoryBibleRecord.id,
            StoryBibleRecord.project_id,
            StoryBibleRecord.concurrency_version,
            StoryBibleRecord.created_at,
            StoryBibleRecord.updated_at,
            ProjectRecord.id,
            StoryBibleHeadRecord.story_bible_id,
            StoryBibleHeadRecord.revision_id,
            StoryBibleHeadRecord.updated_at,
            StoryBibleRevisionRecord.id,
            StoryBibleRevisionRecord.story_bible_id,
            StoryBibleRevisionRecord.revision_number,
            StoryBibleRevisionRecord.created_at,
        )
        .outerjoin(ProjectRecord, ProjectRecord.id == StoryBibleRecord.project_id)
        .outerjoin(
            StoryBibleHeadRecord,
            StoryBibleHeadRecord.story_bible_id == StoryBibleRecord.id,
        )
        .outerjoin(
            StoryBibleRevisionRecord,
            and_(
                StoryBibleRevisionRecord.story_bible_id == StoryBibleHeadRecord.story_bible_id,
                StoryBibleRevisionRecord.id == StoryBibleHeadRecord.revision_id,
            ),
        )
        .where(
            StoryBibleRecord.id == story_bible_id,
            StoryBibleRecord.project_id.not_in(ProjectRecord.deleted_ids()),
        ),
    )


def story_bible_revision_history_statement(
    *,
    story_bible_id: StoryBibleId,
    limit: int,
    after: RevisionNumber | None,
) -> Select[StoryBibleRevisionHistoryRow]:
    """Build the fixed descending keyset query without loading content."""
    statement = select(
        StoryBibleRevisionRecord.id,
        StoryBibleRevisionRecord.revision_number,
        StoryBibleRevisionRecord.title,
        StoryBibleRevisionRecord.created_at,
    ).where(StoryBibleRevisionRecord.story_bible_id == story_bible_id)
    if after is not None:
        statement = statement.where(StoryBibleRevisionRecord.revision_number < after)
    limit_clause = text("LIMIT :story_bible_revision_history_limit").bindparams(
        bindparam(
            "story_bible_revision_history_limit",
            value=limit + 1,
            type_=Integer(),
        )
    )
    return cast(
        Select[StoryBibleRevisionHistoryRow],
        statement.order_by(StoryBibleRevisionRecord.revision_number.desc()).suffix_with(
            limit_clause
        ),
    )


def story_bible_revision_statement(
    *,
    story_bible_id: StoryBibleId,
    revision_number: RevisionNumber,
) -> Select[StoryBibleRevisionSnapshotRow]:
    """Build one exact immutable revision read scoped to its Story Bible."""
    return cast(
        Select[StoryBibleRevisionSnapshotRow],
        select(
            StoryBibleRevisionRecord.id,
            StoryBibleRevisionRecord.revision_number,
            StoryBibleRevisionRecord.title,
            StoryBibleRevisionRecord.content,
            StoryBibleRevisionRecord.created_at,
        ).where(
            StoryBibleRevisionRecord.story_bible_id == story_bible_id,
            StoryBibleRevisionRecord.revision_number == revision_number,
        ),
    )


def _require_utc_time(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise StoryBibleDataCorruption
    return value


def _state_from_row(row: StoryBibleHistoryStateRow) -> _StoryBibleHistoryState:
    (
        story_bible_id,
        project_id,
        concurrency_version,
        created_at_value,
        updated_at_value,
        existing_project_id,
        head_story_bible_id,
        head_revision_id,
        head_updated_at_value,
        revision_id,
        revision_story_bible_id,
        revision_number,
        revision_created_at_value,
    ) = row
    created_at = _require_utc_time(created_at_value)
    updated_at = _require_utc_time(updated_at_value)
    head_updated_at = _require_utc_time(head_updated_at_value)
    revision_created_at = _require_utc_time(revision_created_at_value)
    if (
        type(story_bible_id) is not StoryBibleId
        or type(project_id) is not ProjectId
        or type(existing_project_id) is not ProjectId
        or type(concurrency_version) is not ConcurrencyVersion
        or type(head_story_bible_id) is not StoryBibleId
        or type(head_revision_id) is not StoryBibleRevisionId
        or type(revision_id) is not StoryBibleRevisionId
        or type(revision_story_bible_id) is not StoryBibleId
        or project_id != existing_project_id
        or head_story_bible_id != story_bible_id
        or revision_story_bible_id != story_bible_id
        or head_revision_id != revision_id
        or type(revision_number) is not RevisionNumber
        or int(concurrency_version) != int(revision_number)
        or created_at > updated_at
        or updated_at != head_updated_at
        or updated_at != revision_created_at
    ):
        raise StoryBibleDataCorruption
    return _StoryBibleHistoryState(
        story_bible_id=story_bible_id,
        project_id=project_id,
        current_revision_id=revision_id,
        current_revision_number=revision_number,
        created_at=created_at,
        updated_at=updated_at,
    )


def _history_item_from_row(
    row: StoryBibleRevisionHistoryRow,
    *,
    state: _StoryBibleHistoryState,
) -> StoryBibleRevisionHistoryItem:
    revision_id, revision_number, title, created_at_value = row
    created_at = _require_utc_time(created_at_value)
    if (
        type(revision_id) is not StoryBibleRevisionId
        or type(revision_number) is not RevisionNumber
        or type(title) is not str
        or created_at < state.created_at
        or created_at > state.updated_at
    ):
        raise StoryBibleDataCorruption
    canonical_title = str(StoryBibleTitle(title))
    if canonical_title != title:
        raise StoryBibleDataCorruption
    return StoryBibleRevisionHistoryItem(
        revision_id=str(revision_id),
        revision_number=int(revision_number),
        title=canonical_title,
        created_at=created_at,
        is_current=revision_id == state.current_revision_id,
    )


def _snapshot_from_row(
    row: StoryBibleRevisionSnapshotRow,
    *,
    state: _StoryBibleHistoryState,
) -> StoryBibleRevisionSnapshot:
    revision_id, revision_number, title, content, created_at_value = row
    created_at = _require_utc_time(created_at_value)
    if (
        type(revision_id) is not StoryBibleRevisionId
        or type(revision_number) is not RevisionNumber
        or type(title) is not str
        or type(content) is not str
        or created_at < state.created_at
        or created_at > state.updated_at
    ):
        raise StoryBibleDataCorruption
    canonical_title = str(StoryBibleTitle(title))
    canonical_content = str(StoryBibleContent(content))
    if canonical_title != title or canonical_content != content:
        raise StoryBibleDataCorruption
    return StoryBibleRevisionSnapshot(
        story_bible_id=str(state.story_bible_id),
        project_id=str(state.project_id),
        revision_id=str(revision_id),
        revision_number=int(revision_number),
        title=canonical_title,
        content=canonical_content,
        created_at=created_at,
        is_current=revision_id == state.current_revision_id,
        current_revision_number=int(state.current_revision_number),
    )


class SqlAlchemyStoryBibleRevisionHistoryReader:
    """Read immutable Story Bible revisions with an independent Session per call."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def list_revisions(
        self,
        story_bible_id: StoryBibleId,
        *,
        limit: int,
        after: StoryBibleRevisionHistoryPosition | None,
    ) -> StoryBibleRevisionHistoryPage:
        """Return at most one validated descending keyset page."""
        self._validate_story_bible_id(story_bible_id)
        validated_limit = validate_story_bible_revision_history_limit(limit)
        if after is not None:
            if type(after) is not StoryBibleRevisionHistoryPosition:
                raise TypeError("after must be a StoryBibleRevisionHistoryPosition or None")
            if after.story_bible_id != story_bible_id:
                raise ValueError("after must belong to the requested Story Bible")
        session = self._new_session()
        try:
            state = self._load_state(session, story_bible_id)
            rows = (
                session.execute(
                    story_bible_revision_history_statement(
                        story_bible_id=story_bible_id,
                        limit=validated_limit,
                        after=after.revision_number if after is not None else None,
                    )
                )
                .tuples()
                .all()
            )
            mapped = tuple(_history_item_from_row(row, state=state) for row in rows)
            if not mapped and after is None:
                raise StoryBibleDataCorruption
            items = mapped[:validated_limit]
            has_more = len(mapped) > validated_limit
            page = StoryBibleRevisionHistoryPage(
                story_bible_id=str(story_bible_id),
                project_id=str(state.project_id),
                current_revision_number=int(state.current_revision_number),
                items=items,
                next_position=(
                    StoryBibleRevisionHistoryPosition(
                        story_bible_id=story_bible_id,
                        revision_number=RevisionNumber(items[-1].revision_number),
                    )
                    if has_more
                    else None
                ),
                has_more=has_more,
            )
            session.rollback()
            return page
        except (StoryBibleNotFound, StoryBibleDataCorruption):
            session.rollback()
            raise
        except (DomainError, TypeError, ValueError) as exc:
            session.rollback()
            raise StoryBibleDataCorruption from exc
        except StatementError as exc:
            session.rollback()
            if isinstance(exc.orig, (DomainError, TypeError, ValueError)):
                raise StoryBibleDataCorruption from exc
            raise StoryBibleRepositoryError from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        finally:
            session.close()

    def get_revision(
        self,
        story_bible_id: StoryBibleId,
        revision_number: RevisionNumber,
    ) -> StoryBibleRevisionSnapshot | None:
        """Return one exact immutable revision after validating current state."""
        self._validate_story_bible_id(story_bible_id)
        if type(revision_number) is not RevisionNumber:
            raise TypeError("revision_number must be a RevisionNumber")
        session = self._new_session()
        try:
            state = self._load_state(session, story_bible_id)
            row = (
                session.execute(
                    story_bible_revision_statement(
                        story_bible_id=story_bible_id,
                        revision_number=revision_number,
                    )
                )
                .tuples()
                .one_or_none()
            )
            snapshot = None if row is None else _snapshot_from_row(row, state=state)
            session.rollback()
            return snapshot
        except (StoryBibleNotFound, StoryBibleDataCorruption):
            session.rollback()
            raise
        except (DomainError, TypeError, ValueError) as exc:
            session.rollback()
            raise StoryBibleDataCorruption from exc
        except StatementError as exc:
            session.rollback()
            if isinstance(exc.orig, (DomainError, TypeError, ValueError)):
                raise StoryBibleDataCorruption from exc
            raise StoryBibleRepositoryError from exc
        except SQLAlchemyError as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        except Exception as exc:
            session.rollback()
            raise StoryBibleRepositoryError from exc
        finally:
            session.close()

    @staticmethod
    def _validate_story_bible_id(story_bible_id: StoryBibleId) -> None:
        if type(story_bible_id) is not StoryBibleId:
            raise TypeError("story_bible_id must be a StoryBibleId")

    @staticmethod
    def _load_state(
        session: Session,
        story_bible_id: StoryBibleId,
    ) -> _StoryBibleHistoryState:
        try:
            row = (
                session.execute(story_bible_history_state_statement(story_bible_id))
                .tuples()
                .one_or_none()
            )
            if row is None:
                raise StoryBibleNotFound(story_bible_id)
            return _state_from_row(row)
        except (StoryBibleNotFound, StoryBibleDataCorruption):
            raise
        except (DomainError, TypeError, ValueError) as exc:
            raise StoryBibleDataCorruption from exc

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise StoryBibleRepositoryError from exc


__all__ = [
    "SqlAlchemyStoryBibleRevisionHistoryReader",
    "story_bible_history_state_statement",
    "story_bible_revision_history_statement",
    "story_bible_revision_statement",
]
