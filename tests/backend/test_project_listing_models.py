"""Immutable Project listing model and query invariants."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone

import pytest

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.application.models import (
    ProjectListItem,
    ProjectListPage,
    ProjectListPosition,
)
from aiwebnovel.project.application.queries import (
    DEFAULT_PROJECT_LIST_LIMIT,
    MAX_PROJECT_LIST_LIMIT,
    ListProjectsQuery,
)

pytestmark = pytest.mark.unit

PROJECT_ID = "prj_00000000000000000000000001"
PROJECT_ID_2 = "prj_00000000000000000000000002"
LETTER_PROJECT_ID = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV"
REVISION_ID = "prv_00000000000000000000000003"
LETTER_REVISION_ID = "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV"
NOW = datetime(2026, 6, 1, 2, 3, 4, tzinfo=UTC)


def item(*, project_id: str = PROJECT_ID, created_at: datetime = NOW) -> ProjectListItem:
    return ProjectListItem(
        project_id=project_id,
        current_revision_id=REVISION_ID,
        revision_number=1,
        concurrency_version=1,
        title="Listing title",
        created_at=created_at,
        updated_at=created_at,
        revision_created_at=created_at,
    )


def test_position_is_frozen_and_normalizes_aware_time_to_utc() -> None:
    source = NOW.astimezone(timezone(timedelta(hours=8)))
    position = ProjectListPosition(created_at=source, project_id=PROJECT_ID)

    assert position.created_at == NOW
    assert position.created_at.tzinfo is UTC
    assert repr(position) == (
        "ProjectListPosition(created_at=datetime.datetime(2026, 6, 1, 2, 3, 4, "
        "tzinfo=datetime.timezone.utc), "
        "project_id='prj_00000000000000000000000001')"
    )
    with pytest.raises(FrozenInstanceError):
        position.project_id = PROJECT_ID_2  # type: ignore[misc]


@pytest.mark.parametrize(
    ("created_at", "project_id"),
    [
        (NOW.replace(tzinfo=None), PROJECT_ID),
        (NOW, "invalid"),
        (NOW, LETTER_PROJECT_ID.lower()),
    ],
)
def test_position_rejects_naive_time_and_noncanonical_ids(
    created_at: datetime,
    project_id: str,
) -> None:
    with pytest.raises((DomainError, TypeError, ValueError)):
        ProjectListPosition(created_at=created_at, project_id=project_id)


def test_position_rejects_non_string_id_and_non_datetime_time() -> None:
    with pytest.raises(TypeError):
        ProjectListPosition(created_at=NOW, project_id=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ProjectListPosition(created_at="now", project_id=PROJECT_ID)  # type: ignore[arg-type]


def test_query_defaults_and_boundaries_are_frozen() -> None:
    query = ListProjectsQuery()
    assert query.limit == DEFAULT_PROJECT_LIST_LIMIT == 20
    assert MAX_PROJECT_LIST_LIMIT == 100
    assert ListProjectsQuery(limit=1).limit == 1
    assert ListProjectsQuery(limit=100).limit == 100
    with pytest.raises(FrozenInstanceError):
        query.limit = 1  # type: ignore[misc]


@pytest.mark.parametrize("limit", [0, -1, 101, True, False, 1.0, "1", None])
def test_query_rejects_invalid_limit_without_coercion(limit: object) -> None:
    with pytest.raises(ValueError):
        ListProjectsQuery(limit=limit)  # type: ignore[arg-type]


def test_query_rejects_non_position_after_value() -> None:
    with pytest.raises(TypeError):
        ListProjectsQuery(after=object())  # type: ignore[arg-type]


def test_list_item_is_detached_frozen_and_omits_description() -> None:
    value = item()
    assert value.title == "Listing title"
    assert value.created_at.tzinfo is UTC
    assert {field.name for field in fields(value)} == {
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "created_at",
        "updated_at",
        "revision_created_at",
    }
    with pytest.raises(FrozenInstanceError):
        value.title = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"project_id": "bad"},
        {"current_revision_id": "bad"},
        {"current_revision_id": LETTER_REVISION_ID.lower()},
        {"current_revision_id": 1},
        {"revision_number": True},
        {"concurrency_version": 0},
        {"title": "\x01"},
        {"title": 1},
        {"created_at": NOW.replace(tzinfo=None)},
        {"created_at": "now"},
        {"updated_at": NOW - timedelta(seconds=1)},
        {"revision_created_at": NOW - timedelta(seconds=1)},
    ],
)
def test_list_item_rejects_invalid_boundary_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "current_revision_id": REVISION_ID,
        "revision_number": 1,
        "concurrency_version": 1,
        "title": "Valid",
        "created_at": NOW,
        "updated_at": NOW,
        "revision_created_at": NOW,
    }
    values.update(overrides)
    with pytest.raises((DomainError, TypeError, ValueError)):
        ProjectListItem(**values)  # type: ignore[arg-type]


def test_empty_and_final_pages_have_no_next_position() -> None:
    assert ProjectListPage(items=(), next_position=None, has_more=False).items == ()
    final = ProjectListPage(items=(item(),), next_position=None, has_more=False)
    assert final.has_more is False


def test_continuing_page_requires_last_item_position() -> None:
    first = item(project_id=PROJECT_ID_2)
    second = item(project_id=PROJECT_ID)
    position = ProjectListPosition(created_at=second.created_at, project_id=second.project_id)
    page = ProjectListPage(items=(first, second), next_position=position, has_more=True)
    assert page.next_position == position
    with pytest.raises(FrozenInstanceError):
        page.has_more = False  # type: ignore[misc]


@pytest.mark.parametrize(
    "page",
    [
        lambda: ProjectListPage(items=[], next_position=None, has_more=False),
        lambda: ProjectListPage(items=(object(),), next_position=None, has_more=False),
        lambda: ProjectListPage(items=(), next_position=None, has_more=1),
        lambda: ProjectListPage(items=(), next_position=object(), has_more=False),
        lambda: ProjectListPage(items=(), next_position=None, has_more=True),
        lambda: ProjectListPage(items=(item(),), next_position=None, has_more=True),
        lambda: ProjectListPage(
            items=(item(),),
            next_position=ProjectListPosition(created_at=NOW, project_id=PROJECT_ID),
            has_more=False,
        ),
        lambda: ProjectListPage(
            items=(item(project_id=PROJECT_ID), item(project_id=PROJECT_ID_2)),
            next_position=None,
            has_more=False,
        ),
    ],
)
def test_page_rejects_invalid_shape_order_and_cursor_invariants(page: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        page()  # type: ignore[operator]
