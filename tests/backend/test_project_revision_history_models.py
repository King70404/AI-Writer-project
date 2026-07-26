"""Immutable Project revision-history application model invariants."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime

import pytest

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.application.models import (
    ProjectRevisionHistoryItem,
    ProjectRevisionHistoryPage,
    ProjectRevisionHistoryPosition,
    ProjectRevisionHistorySnapshot,
)
from aiwebnovel.project.application.queries import (
    DEFAULT_PROJECT_REVISION_HISTORY_LIMIT,
    MAX_PROJECT_REVISION_HISTORY_LIMIT,
    GetProjectRevisionQuery,
    ListProjectRevisionsQuery,
)

pytestmark = pytest.mark.unit

PROJECT_ID = "prj_00000000000000000000000001"
OTHER_PROJECT_ID = "prj_00000000000000000000000002"
LETTER_PROJECT_ID = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV"
REVISION_ID = "prv_00000000000000000000000003"
OTHER_REVISION_ID = "prv_00000000000000000000000004"
LETTER_REVISION_ID = "prv_01ARZ3NDEKTSV4RRFFQ69G5FAV"
NOW = datetime(2026, 7, 1, 2, 3, 4, tzinfo=UTC)


def item(
    number: int = 2,
    *,
    revision_id: str = REVISION_ID,
    current: bool = True,
) -> ProjectRevisionHistoryItem:
    return ProjectRevisionHistoryItem(
        revision_id=revision_id,
        revision_number=number,
        title=f"Revision {number}",
        created_at=NOW,
        is_current=current,
    )


def test_position_and_queries_are_frozen_and_use_bounded_limits() -> None:
    position = ProjectRevisionHistoryPosition(PROJECT_ID, 2)
    query = ListProjectRevisionsQuery(PROJECT_ID, after=position)

    assert query.limit == DEFAULT_PROJECT_REVISION_HISTORY_LIMIT == 20
    assert MAX_PROJECT_REVISION_HISTORY_LIMIT == 100
    assert ListProjectRevisionsQuery(PROJECT_ID, limit=1).limit == 1
    assert ListProjectRevisionsQuery(PROJECT_ID, limit=100).limit == 100
    assert GetProjectRevisionQuery(PROJECT_ID, 1).revision_number == 1
    assert repr(position) == (
        "ProjectRevisionHistoryPosition(project_id="
        "'prj_00000000000000000000000001', revision_number=2)"
    )
    with pytest.raises(FrozenInstanceError):
        position.revision_number = 1  # type: ignore[misc]


@pytest.mark.parametrize("limit", [0, -1, 101, True, False, 1.0, "1", None])
def test_query_rejects_non_integer_or_out_of_range_limits(limit: object) -> None:
    with pytest.raises(ValueError):
        ListProjectRevisionsQuery(PROJECT_ID, limit=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("project_id", "number"),
    [("bad", 1), (LETTER_PROJECT_ID.lower(), 1), (PROJECT_ID, 0), (PROJECT_ID, True)],
)
def test_position_rejects_invalid_values(project_id: str, number: object) -> None:
    with pytest.raises((DomainError, TypeError, ValueError)):
        ProjectRevisionHistoryPosition(project_id, number)  # type: ignore[arg-type]


def test_history_item_is_exact_detached_summary_without_description() -> None:
    value = item()
    assert {field.name for field in fields(value)} == {
        "revision_id",
        "revision_number",
        "title",
        "created_at",
        "is_current",
    }
    assert not hasattr(value, "description")
    assert value.created_at.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        value.title = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"revision_id": "bad"},
        {"revision_id": 1},
        {"revision_id": LETTER_REVISION_ID.lower()},
        {"revision_number": True},
        {"title": "\x01"},
        {"title": 1},
        {"created_at": NOW.replace(tzinfo=None)},
        {"is_current": 1},
    ],
)
def test_history_item_rejects_invalid_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "revision_id": REVISION_ID,
        "revision_number": 2,
        "title": "Revision 2",
        "created_at": NOW,
        "is_current": True,
    }
    values.update(overrides)
    with pytest.raises((DomainError, TypeError, ValueError)):
        ProjectRevisionHistoryItem(**values)  # type: ignore[arg-type]


def test_page_accepts_descending_current_and_continuing_position() -> None:
    items = (
        item(3, revision_id=OTHER_REVISION_ID, current=True),
        item(2, current=False),
    )
    position = ProjectRevisionHistoryPosition(PROJECT_ID, 2)
    page = ProjectRevisionHistoryPage(PROJECT_ID, 3, items, position, True)

    assert page.items == items
    assert page.next_position == position
    with pytest.raises(FrozenInstanceError):
        page.has_more = False  # type: ignore[misc]


def test_page_allows_empty_final_position_for_beyond_end_cursor() -> None:
    page = ProjectRevisionHistoryPage(PROJECT_ID, 3, (), None, False)
    assert page.items == ()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ProjectRevisionHistoryPage(PROJECT_ID, 2, [], None, False),
        lambda: ProjectRevisionHistoryPage(PROJECT_ID, 2, (object(),), None, False),
        lambda: ProjectRevisionHistoryPage(PROJECT_ID, 2, (item(),), None, True),
        lambda: ProjectRevisionHistoryPage(
            PROJECT_ID,
            2,
            (item(),),
            ProjectRevisionHistoryPosition(OTHER_PROJECT_ID, 2),
            True,
        ),
        lambda: ProjectRevisionHistoryPage(
            PROJECT_ID,
            2,
            (item(),),
            ProjectRevisionHistoryPosition(PROJECT_ID, 2),
            False,
        ),
        lambda: ProjectRevisionHistoryPage(
            PROJECT_ID,
            2,
            (item(1, current=False), item(2)),
            None,
            False,
        ),
        lambda: ProjectRevisionHistoryPage(
            PROJECT_ID,
            2,
            (item(2), item(2, revision_id=OTHER_REVISION_ID)),
            None,
            False,
        ),
        lambda: ProjectRevisionHistoryPage(
            PROJECT_ID,
            2,
            (item(2), item(1, revision_id=REVISION_ID, current=False)),
            None,
            False,
        ),
        lambda: ProjectRevisionHistoryPage(
            PROJECT_ID,
            2,
            (item(2, current=False),),
            None,
            False,
        ),
    ],
)
def test_page_rejects_shape_order_duplicate_and_current_inconsistency(factory: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def test_snapshot_is_exact_frozen_complete_content() -> None:
    snapshot = ProjectRevisionHistorySnapshot(
        project_id=PROJECT_ID,
        revision_id=REVISION_ID,
        revision_number=1,
        title="Original",
        description="Line one\nLine two",
        created_at=NOW,
        is_current=False,
        current_revision_number=2,
    )
    assert {field.name for field in fields(snapshot)} == {
        "project_id",
        "revision_id",
        "revision_number",
        "title",
        "description",
        "created_at",
        "is_current",
        "current_revision_number",
    }
    with pytest.raises(FrozenInstanceError):
        snapshot.description = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"project_id": "bad"},
        {"revision_id": "bad"},
        {"revision_number": 0},
        {"title": 1},
        {"description": 1},
        {"created_at": NOW.replace(tzinfo=None)},
        {"is_current": 1},
        {"is_current": True},
        {"current_revision_number": True},
    ],
)
def test_snapshot_rejects_invalid_values_and_current_relation(
    overrides: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "revision_id": REVISION_ID,
        "revision_number": 1,
        "title": "Original",
        "description": "Body",
        "created_at": NOW,
        "is_current": False,
        "current_revision_number": 2,
    }
    values.update(overrides)
    with pytest.raises((DomainError, TypeError, ValueError)):
        ProjectRevisionHistorySnapshot(**values)  # type: ignore[arg-type]
