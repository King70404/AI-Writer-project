"""Single-query SQLAlchemy adapter for stable Project keyset pages."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import cast

from sqlalchemy import Integer, Select, and_, bindparam, or_, select, text
from sqlalchemy.exc import SQLAlchemyError, StatementError
from sqlalchemy.orm import Session

from aiwebnovel.project import ConcurrencyVersion, RevisionNumber
from aiwebnovel.project.application.models import (
    ProjectListItem,
    ProjectListPage,
    ProjectListPosition,
)
from aiwebnovel.project.application.queries import validate_project_list_limit
from aiwebnovel.project.errors import (
    DomainError,
    ProjectDataCorruption,
    ProjectRepositoryError,
)
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.models import (
    ProjectHeadRecord,
    ProjectRecord,
    ProjectRevisionRecord,
)
from aiwebnovel.project.values import ProjectTitle

SessionFactory = Callable[[], Session]
ProjectListRow = tuple[
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


def project_list_statement(
    *,
    limit: int,
    after: ProjectListPosition | None,
) -> Select[ProjectListRow]:
    """Build the fixed current-revision query with descending keyset semantics."""
    statement = (
        select(
            ProjectRecord.id,
            ProjectRecord.concurrency_version,
            ProjectRecord.created_at,
            ProjectRecord.updated_at,
            ProjectHeadRecord.project_id,
            ProjectHeadRecord.revision_id,
            ProjectHeadRecord.updated_at,
            ProjectRevisionRecord.id,
            ProjectRevisionRecord.project_id,
            ProjectRevisionRecord.revision_number,
            ProjectRevisionRecord.title,
            ProjectRevisionRecord.created_at,
        )
        .outerjoin(
            ProjectHeadRecord,
            ProjectHeadRecord.project_id == ProjectRecord.id,
        )
        .outerjoin(
            ProjectRevisionRecord,
            ProjectRevisionRecord.id == ProjectHeadRecord.revision_id,
        )
    )
    if after is not None:
        after_project_id = ProjectId.parse(after.project_id)
        statement = statement.where(
            or_(
                ProjectRecord.created_at < after.created_at,
                and_(
                    ProjectRecord.created_at == after.created_at,
                    ProjectRecord.id < after_project_id,
                ),
            )
        )
    limit_clause = text("LIMIT :project_list_limit").bindparams(
        bindparam("project_list_limit", value=limit + 1, type_=Integer())
    )
    statement = statement.order_by(
        ProjectRecord.created_at.desc(),
        ProjectRecord.id.desc(),
    ).suffix_with(
        # SQLAlchemy's SQLite ``limit()`` compiler emits an explicit OFFSET 0.
        # A fixed suffix retains a bound page-size parameter without OFFSET.
        limit_clause
    )
    return cast(Select[ProjectListRow], statement)


def _list_item_from_row(row: ProjectListRow) -> ProjectListItem:
    (
        project_id,
        concurrency_version,
        project_created_at,
        project_updated_at,
        head_project_id,
        head_revision_id,
        head_updated_at,
        revision_id,
        revision_project_id,
        revision_number,
        title,
        revision_created_at,
    ) = row
    if (
        type(project_id) is not ProjectId
        or type(concurrency_version) is not ConcurrencyVersion
        or type(project_created_at) is not datetime
        or type(project_updated_at) is not datetime
        or type(head_project_id) is not ProjectId
        or type(head_revision_id) is not ProjectRevisionId
        or type(head_updated_at) is not datetime
        or type(revision_id) is not ProjectRevisionId
        or type(revision_project_id) is not ProjectId
        or type(revision_number) is not RevisionNumber
        or type(title) is not str
        or type(revision_created_at) is not datetime
    ):
        raise ProjectDataCorruption
    if (
        head_project_id != project_id
        or revision_project_id != project_id
        or head_revision_id != revision_id
        or project_updated_at < project_created_at
        or revision_created_at < project_created_at
        or project_updated_at < revision_created_at
        or head_updated_at < revision_created_at
    ):
        raise ProjectDataCorruption
    canonical_title = str(ProjectTitle(title))
    if canonical_title != title:
        raise ProjectDataCorruption
    return ProjectListItem(
        project_id=str(project_id),
        current_revision_id=str(revision_id),
        revision_number=int(revision_number),
        concurrency_version=int(concurrency_version),
        title=canonical_title,
        created_at=project_created_at,
        updated_at=project_updated_at,
        revision_created_at=revision_created_at,
    )


class SqlAlchemyProjectListReader:
    """Read one current Project page with one independent Session and SELECT."""

    def __init__(self, session_factory: SessionFactory) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._session_factory = session_factory

    def list_page(
        self,
        *,
        limit: int,
        after: ProjectListPosition | None,
    ) -> ProjectListPage:
        """Return at most ``limit`` summaries using an immutable descending keyset."""
        validated_limit = validate_project_list_limit(limit)
        if after is not None and type(after) is not ProjectListPosition:
            raise TypeError("after must be a ProjectListPosition or None")
        session = self._new_session()
        try:
            rows = (
                session.execute(project_list_statement(limit=validated_limit, after=after))
                .tuples()
                .all()
            )
            items = tuple(_list_item_from_row(row) for row in rows[:validated_limit])
            has_more = len(rows) > validated_limit
            next_position = (
                ProjectListPosition(
                    created_at=items[-1].created_at,
                    project_id=items[-1].project_id,
                )
                if has_more
                else None
            )
            page = ProjectListPage(
                items=items,
                next_position=next_position,
                has_more=has_more,
            )
            session.rollback()
            return page
        except ProjectDataCorruption:
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

    def _new_session(self) -> Session:
        try:
            return self._session_factory()
        except Exception as exc:
            raise ProjectRepositoryError from exc


__all__ = ["SqlAlchemyProjectListReader", "project_list_statement"]
