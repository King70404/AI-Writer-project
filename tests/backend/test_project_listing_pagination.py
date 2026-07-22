"""Stable Project list keyset traversal under revisions and new inserts."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.backend.project_repository_support import (
    BASE_TIME,
    RepositoryDatabase,
    aggregate,
    project_id,
    repository_database,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.project.persistence.listing import SqlAlchemyProjectListReader
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


def _seed_five(database: RepositoryDatabase) -> None:
    repository = database.repository
    for value in range(1, 6):
        repository.create(aggregate(value, created_at=BASE_TIME + timedelta(seconds=value)))


def test_static_dataset_traversal_has_no_duplicates_or_omissions(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        _seed_five(database)
        reader = SqlAlchemyProjectListReader(database.session_factory)
        observed: list[str] = []
        after = None
        while True:
            page = reader.list_page(limit=2, after=after)
            observed.extend(item.project_id for item in page.items)
            if not page.has_more:
                break
            assert page.next_position is not None
            after = page.next_position

    expected = [str(project_id(value)) for value in range(5, 0, -1)]
    assert observed == expected
    assert len(observed) == len(set(observed)) == 5


def test_revision_changes_content_without_changing_pagination_position(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        _seed_five(database)
        reader = SqlAlchemyProjectListReader(database.session_factory)
        first = reader.list_page(limit=2, after=None)
        assert first.next_position is not None
        database.repository.append_revision(
            project_id(3),
            ConcurrencyVersion(1),
            ProjectTitle("Revised while paging"),
            ProjectDescription("Current content"),
            clock=lambda: BASE_TIME + timedelta(seconds=20),
        )
        second = reader.list_page(limit=2, after=first.next_position)

    assert [item.project_id for item in first.items] == [str(project_id(5)), str(project_id(4))]
    assert [item.project_id for item in second.items] == [str(project_id(3)), str(project_id(2))]
    assert second.items[0].title == "Revised while paging"
    assert second.items[0].created_at == BASE_TIME + timedelta(seconds=3)
    assert second.items[0].updated_at == BASE_TIME + timedelta(seconds=20)


def test_new_project_is_excluded_from_old_cursor_but_leads_a_new_first_page(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        _seed_five(database)
        reader = SqlAlchemyProjectListReader(database.session_factory)
        first = reader.list_page(limit=2, after=None)
        assert first.next_position is not None
        database.repository.create(aggregate(6, created_at=BASE_TIME + timedelta(seconds=30)))
        remaining: list[str] = []
        after = first.next_position
        while True:
            page = reader.list_page(limit=2, after=after)
            remaining.extend(item.project_id for item in page.items)
            if not page.has_more:
                break
            assert page.next_position is not None
            after = page.next_position
        new_first = reader.list_page(limit=2, after=None)

    assert str(project_id(6)) not in remaining
    assert remaining == [str(project_id(3)), str(project_id(2)), str(project_id(1))]
    assert new_first.items[0].project_id == str(project_id(6))
