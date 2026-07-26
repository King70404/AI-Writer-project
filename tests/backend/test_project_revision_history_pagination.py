"""Stable RevisionNumber keyset traversal tests for immutable history."""

from pathlib import Path

import pytest
from tests.backend.project_repository_support import repository_database, revision_id
from tests.backend.test_project_revision_history_persistence import append_revisions

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.application.models import ProjectRevisionHistoryPosition
from aiwebnovel.project.persistence.history import SqlAlchemyProjectRevisionHistoryReader
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


def test_limit_plus_one_and_multi_page_traversal_have_no_duplicates_or_omissions(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=21)
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        first = reader.list_page(project_id=current.project.id, limit=20, after=None)
        assert [item.revision_number for item in first.items] == list(range(21, 1, -1))
        assert first.has_more is True
        assert first.next_position == ProjectRevisionHistoryPosition(str(current.project.id), 2)
        second = reader.list_page(
            project_id=current.project.id,
            limit=20,
            after=RevisionNumber(first.next_position.revision_number),
        )

    numbers = [item.revision_number for item in (*first.items, *second.items)]
    assert numbers == list(range(21, 0, -1))
    assert len(numbers) == len(set(numbers)) == 21
    assert second.has_more is False
    assert second.next_position is None


def test_new_revision_does_not_make_an_old_cursor_repeat_older_rows(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=4)
        reader = SqlAlchemyProjectRevisionHistoryReader(database.session_factory)
        first = reader.list_page(project_id=current.project.id, limit=2, after=None)
        assert first.next_position is not None
        old_after = RevisionNumber(first.next_position.revision_number)

        latest = database.repository.append_revision(
            current.project.id,
            ConcurrencyVersion(4),
            ProjectTitle("History 5"),
            ProjectDescription("History body 5"),
            clock=lambda: current.project.updated_at,
            revision_id_factory=lambda: revision_id(40_005),
        )
        continued = reader.list_page(
            project_id=current.project.id,
            limit=2,
            after=old_after,
        )
        refreshed = reader.list_page(project_id=current.project.id, limit=2, after=None)

    assert [item.revision_number for item in first.items] == [4, 3]
    assert [item.revision_number for item in continued.items] == [2, 1]
    assert [item.revision_number for item in refreshed.items] == [5, 4]
    assert latest.current_revision.revision_number == RevisionNumber(5)


def test_beyond_end_position_returns_empty_final_page_for_existing_project(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        current = append_revisions(database, count=1)
        page = SqlAlchemyProjectRevisionHistoryReader(database.session_factory).list_page(
            project_id=current.project.id,
            limit=20,
            after=RevisionNumber(1),
        )
    assert page.items == ()
    assert page.has_more is False
    assert page.current_revision_number == 1
