"""Chapter operations in a caller-owned transaction; never commits independently."""

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.novel_structure.entities import ChapterAggregate
from aiwebnovel.novel_structure.errors import ChapterNotFound, NovelStructureDataCorruption
from aiwebnovel.novel_structure.identifiers import ChapterId, ChapterRevisionId
from aiwebnovel.novel_structure.persistence.mappers import (
    chapter_aggregate_from_records,
    chapter_revision_to_record,
)
from aiwebnovel.novel_structure.persistence.models import ChapterRecord
from aiwebnovel.novel_structure.persistence.queries import (
    chapter_head_compare_and_swap,
    current_chapter_query,
    stable_compare_and_swap,
)
from aiwebnovel.novel_structure.transitions import append_chapter_content_revision
from aiwebnovel.novel_structure.values import ManuscriptContent
from aiwebnovel.project.persistence.models import ProjectRecord


def load_workflow_chapter(session: Session, chapter_id: str) -> ChapterAggregate:
    row = session.execute(
        current_chapter_query(ChapterId.parse(chapter_id)).where(
            ChapterRecord.project_id.in_(ProjectRecord.active_ids())
        )
    ).one_or_none()
    if row is None:
        raise ChapterNotFound
    stable, project_id, volume_project_id, head, revision = row
    if (
        project_id != stable.project_id
        or volume_project_id != stable.project_id
        or head is None
        or revision is None
    ):
        raise NovelStructureDataCorruption
    return chapter_aggregate_from_records(stable, head, revision)


def adopt_workflow_content(
    session: Session, current: ChapterAggregate, content: str, expected_version: int
) -> ChapterAggregate:
    expected = ConcurrencyVersion(expected_version)
    assert_expected_version(current.chapter.concurrency_version, expected)
    next_aggregate = append_chapter_content_revision(
        current,
        expected_version=expected,
        revision_id=ChapterRevisionId.new(),
        content=ManuscriptContent(content),
        now=datetime.now(UTC),
    )
    session.add(chapter_revision_to_record(next_aggregate.current_revision))
    session.flush()
    statements = (
        stable_compare_and_swap(
            ChapterRecord,
            current.chapter.id,
            expected,
            next_aggregate.chapter.concurrency_version,
            next_aggregate.chapter.updated_at,
        ),
        chapter_head_compare_and_swap(
            current.chapter.id,
            current.head.revision_id,
            next_aggregate.head.revision_id,
            next_aggregate.head.updated_at,
        ),
    )
    for statement in statements:
        if cast(CursorResult[Any], session.execute(statement)).rowcount != 1:
            raise NovelStructureDataCorruption
    return next_aggregate
