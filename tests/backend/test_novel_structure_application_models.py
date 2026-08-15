"""Primitive application contracts and explicit novel-structure snapshots."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta

import pytest
from tests.backend.novel_structure_support import (
    BASE_TIME,
    chapter_id,
    chapter_revision_id,
    initial_chapter,
    initial_outline,
    initial_volume,
    outline_id,
    outline_revision_id,
    project_id,
    volume_id,
    volume_revision_id,
)

from aiwebnovel.novel_structure.application.commands import (
    CreateChapterCommand,
    CreateOutlineCommand,
    CreateVolumeCommand,
    UpdateChapterCommand,
    UpdateOutlineCommand,
    UpdateVolumeCommand,
)
from aiwebnovel.novel_structure.application.mappers import (
    chapter_snapshot_from_aggregate,
    outline_snapshot_from_aggregate,
    volume_snapshot_from_aggregate,
)
from aiwebnovel.novel_structure.application.models import (
    ChapterSnapshot,
    OutlineSnapshot,
    VolumeSnapshot,
)
from aiwebnovel.novel_structure.application.queries import (
    GetChapterQuery,
    GetOutlineForProjectQuery,
    GetOutlineQuery,
    GetVolumeQuery,
    ListChaptersQuery,
    ListVolumesQuery,
)
from aiwebnovel.novel_structure.errors import (
    InvalidNovelStructurePosition,
    InvalidNovelStructureState,
    InvalidNovelStructureSummary,
    InvalidNovelStructureTitle,
)


@pytest.mark.parametrize(
    ("model", "expected_fields"),
    [
        (
            CreateOutlineCommand(str(project_id()), "title", "summary"),
            ("project_id", "title", "summary"),
        ),
        (
            UpdateOutlineCommand(str(outline_id()), 1, "title", "summary"),
            ("outline_id", "expected_version", "title", "summary"),
        ),
        (
            CreateVolumeCommand(str(project_id()), "title", "summary", 1),
            ("project_id", "title", "summary", "position"),
        ),
        (
            UpdateVolumeCommand(str(volume_id()), 1, "title", "summary", 1),
            ("volume_id", "expected_version", "title", "summary", "position"),
        ),
        (
            CreateChapterCommand(str(project_id()), str(volume_id()), "title", "summary", 1),
            ("project_id", "volume_id", "title", "summary", "position"),
        ),
        (
            UpdateChapterCommand(str(chapter_id()), 1, "title", "summary", 1),
            ("chapter_id", "expected_version", "title", "summary", "position"),
        ),
        (GetOutlineQuery(str(outline_id())), ("outline_id",)),
        (GetOutlineForProjectQuery(str(project_id())), ("project_id",)),
        (GetVolumeQuery(str(volume_id())), ("volume_id",)),
        (ListVolumesQuery(str(project_id())), ("project_id",)),
        (GetChapterQuery(str(chapter_id())), ("chapter_id",)),
        (ListChaptersQuery(str(volume_id())), ("volume_id",)),
    ],
)
def test_command_and_query_contracts_are_exact_immutable_primitives(
    model: object,
    expected_fields: tuple[str, ...],
) -> None:
    assert tuple(field.name for field in fields(model)) == expected_fields
    with pytest.raises(FrozenInstanceError):
        setattr(model, expected_fields[0], "changed")


def test_mappers_return_complete_detached_snapshots() -> None:
    outline = outline_snapshot_from_aggregate(initial_outline())
    volume = volume_snapshot_from_aggregate(initial_volume())
    chapter = chapter_snapshot_from_aggregate(initial_chapter())

    assert outline == OutlineSnapshot(
        str(outline_id()),
        str(project_id()),
        str(outline_revision_id()),
        1,
        1,
        "总纲",
        "全书规划",
        BASE_TIME,
        BASE_TIME,
        BASE_TIME,
    )
    assert volume == VolumeSnapshot(
        str(volume_id()),
        str(project_id()),
        str(volume_revision_id()),
        1,
        1,
        "第一卷",
        "卷规划",
        1,
        BASE_TIME,
        BASE_TIME,
        BASE_TIME,
    )
    assert chapter == ChapterSnapshot(
        str(chapter_id()),
        str(project_id()),
        str(volume_id()),
        str(chapter_revision_id()),
        1,
        1,
        "第一章",
        "章节规划",
        1,
        BASE_TIME,
        BASE_TIME,
        BASE_TIME,
    )
    assert not hasattr(chapter, "body")
    assert not hasattr(chapter, "content")


@pytest.mark.parametrize(
    "mapper",
    [
        outline_snapshot_from_aggregate,
        volume_snapshot_from_aggregate,
        chapter_snapshot_from_aggregate,
    ],
)
def test_mappers_reject_non_aggregates(mapper) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidNovelStructureState):
        mapper(object())


def _valid_outline(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "outline_id": str(outline_id()),
        "project_id": str(project_id()),
        "current_revision_id": str(outline_revision_id()),
        "revision_number": 1,
        "concurrency_version": 1,
        "title": "Title",
        "summary": "Summary",
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
        "revision_created_at": BASE_TIME,
    }
    values.update(changes)
    return values


@pytest.mark.parametrize(
    ("changes", "error_type"),
    [
        ({"outline_id": 1}, TypeError),
        ({"outline_id": str(outline_id(10)).lower()}, Exception),
        ({"project_id": 1}, TypeError),
        ({"project_id": str(project_id(10)).lower()}, ValueError),
        ({"current_revision_id": 1}, TypeError),
        ({"revision_number": True}, TypeError),
        ({"concurrency_version": True}, TypeError),
        ({"revision_number": 2}, ValueError),
        ({"title": 1}, TypeError),
        ({"title": "\x00"}, InvalidNovelStructureTitle),
        ({"summary": 1}, TypeError),
        ({"summary": "\x00"}, InvalidNovelStructureSummary),
        ({"created_at": "not-time"}, TypeError),
        ({"created_at": datetime(2026, 1, 1)}, ValueError),
        ({"created_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
        ({"revision_created_at": BASE_TIME + timedelta(seconds=1)}, ValueError),
    ],
)
def test_outline_snapshot_rejects_invalid_primitives(
    changes: dict[str, object],
    error_type: type[BaseException],
) -> None:
    with pytest.raises(error_type):
        OutlineSnapshot(**_valid_outline(**changes))  # type: ignore[arg-type]


def test_snapshots_normalize_valid_values_and_are_immutable() -> None:
    offset_time = datetime(2026, 1, 2, 11, 4, 5, tzinfo=UTC) - timedelta(hours=8)
    snapshot = OutlineSnapshot(**_valid_outline(title="  Title  ", created_at=offset_time))  # type: ignore[arg-type]
    assert snapshot.title == "Title"
    assert snapshot.created_at.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        snapshot.title = "changed"


@pytest.mark.parametrize("position", [True, 0, -1, 1 << 63])
def test_position_snapshots_reject_invalid_position(position: object) -> None:
    with pytest.raises((TypeError, InvalidNovelStructurePosition)):
        VolumeSnapshot(
            str(volume_id()),
            str(project_id()),
            str(volume_revision_id()),
            1,
            1,
            "Title",
            "",
            position,  # type: ignore[arg-type]
            BASE_TIME,
            BASE_TIME,
            BASE_TIME,
        )
