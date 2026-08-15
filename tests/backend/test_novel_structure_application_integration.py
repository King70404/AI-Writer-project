"""Real migrated-repository application flows for Outline, Volume, and Chapter."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.backend.novel_structure_repository_support import (
    BASE_TIME,
    chapter_id,
    chapter_revision_id,
    create_project,
    outline_id,
    outline_revision_id,
    project_aggregate,
    project_id,
    repository_database,
    volume_id,
    volume_revision_id,
)

from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.novel_structure.application.commands import (
    CreateChapterCommand,
    CreateOutlineCommand,
    CreateVolumeCommand,
    UpdateChapterCommand,
    UpdateOutlineCommand,
    UpdateVolumeCommand,
)
from aiwebnovel.novel_structure.application.queries import (
    GetChapterQuery,
    GetOutlineForProjectQuery,
    GetOutlineQuery,
    GetVolumeQuery,
    ListChaptersQuery,
    ListVolumesQuery,
)
from aiwebnovel.novel_structure.application.services import (
    NovelStructureCommandService,
    NovelStructureQueryService,
)
from aiwebnovel.novel_structure.errors import (
    ChapterPositionConflict,
    ChapterVolumeOwnershipMismatch,
    OutlineAlreadyExists,
    VolumeNotFound,
    VolumePositionConflict,
)
from aiwebnovel.project.errors import ProjectNotFound

pytestmark = pytest.mark.integration


def _factories(values):  # type: ignore[no-untyped-def]
    iterator = iter(values)
    return lambda: next(iterator)


def test_real_repository_complete_application_flow(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        owner = create_project(database)
        command_service = NovelStructureCommandService(
            database.repository,
            database.project_repository,
            _factories(
                [
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME,
                    BASE_TIME + timedelta(seconds=1),
                    BASE_TIME + timedelta(seconds=1),
                    BASE_TIME + timedelta(seconds=1),
                ]
            ),
            _factories([outline_id(101)]),
            _factories([outline_revision_id(10_101), outline_revision_id(10_102)]),
            _factories([volume_id(201), volume_id(202)]),
            _factories(
                [
                    volume_revision_id(10_201),
                    volume_revision_id(10_202),
                    volume_revision_id(10_203),
                ]
            ),
            _factories([chapter_id(301), chapter_id(302)]),
            _factories(
                [
                    chapter_revision_id(10_301),
                    chapter_revision_id(10_302),
                    chapter_revision_id(10_303),
                ]
            ),
        )
        query_service = NovelStructureQueryService(
            database.repository,
            database.project_repository,
        )

        outline = command_service.create_outline(
            CreateOutlineCommand(str(owner.project.id), "  Outline 1  ", "first\r\nsummary")
        )
        volume_two = command_service.create_volume(
            CreateVolumeCommand(str(owner.project.id), "Volume 2", "", 2)
        )
        volume_one = command_service.create_volume(
            CreateVolumeCommand(str(owner.project.id), "Volume 1", "", 1)
        )
        chapter_two = command_service.create_chapter(
            CreateChapterCommand(str(owner.project.id), volume_one.volume_id, "Chapter 2", "", 2)
        )
        chapter_one = command_service.create_chapter(
            CreateChapterCommand(str(owner.project.id), volume_one.volume_id, "Chapter 1", "", 1)
        )

        assert outline.revision_number == outline.concurrency_version == 1
        assert outline.title == "Outline 1"
        assert outline.summary == "first\nsummary"
        assert query_service.get_outline(GetOutlineQuery(outline.outline_id)) == outline
        assert (
            query_service.get_outline_for_project(GetOutlineForProjectQuery(str(owner.project.id)))
            == outline
        )
        assert query_service.get_volume(GetVolumeQuery(volume_one.volume_id)) == volume_one
        assert query_service.get_chapter(GetChapterQuery(chapter_one.chapter_id)) == chapter_one
        assert [
            item.volume_id
            for item in query_service.list_volumes(ListVolumesQuery(str(owner.project.id)))
        ] == [volume_one.volume_id, volume_two.volume_id]
        assert [
            item.chapter_id
            for item in query_service.list_chapters(ListChaptersQuery(volume_one.volume_id))
        ] == [chapter_one.chapter_id, chapter_two.chapter_id]

        revised_outline = command_service.update_outline(
            UpdateOutlineCommand(outline.outline_id, 1, "Outline 2", "replacement")
        )
        revised_volume = command_service.update_volume(
            UpdateVolumeCommand(volume_two.volume_id, 1, "Volume 2 updated", "new", 3)
        )
        revised_chapter = command_service.update_chapter(
            UpdateChapterCommand(chapter_two.chapter_id, 1, "Chapter 2 updated", "new", 3)
        )

        assert revised_outline.revision_number == revised_outline.concurrency_version == 2
        assert revised_volume.revision_number == revised_volume.concurrency_version == 2
        assert revised_volume.position == 3
        assert revised_chapter.revision_number == revised_chapter.concurrency_version == 2
        assert revised_chapter.position == 3
        assert revised_outline.project_id == outline.project_id
        assert revised_volume.project_id == volume_two.project_id
        assert revised_chapter.project_id == chapter_two.project_id
        assert revised_chapter.volume_id == chapter_two.volume_id

        with pytest.raises(ConcurrencyConflict):
            command_service.update_outline(
                UpdateOutlineCommand(outline.outline_id, 1, "stale", "stale")
            )
        with pytest.raises(ConcurrencyConflict):
            command_service.update_volume(
                UpdateVolumeCommand(volume_two.volume_id, 1, "stale", "", 4)
            )
        with pytest.raises(ConcurrencyConflict):
            command_service.update_chapter(
                UpdateChapterCommand(chapter_two.chapter_id, 1, "stale", "", 4)
            )

        with database.engine.connect() as connection:
            counts = {
                table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
                for table in (
                    "outlines",
                    "outline_revisions",
                    "outline_heads",
                    "volumes",
                    "volume_revisions",
                    "volume_heads",
                    "chapters",
                    "chapter_revisions",
                    "chapter_heads",
                )
            }
            owner_version = connection.exec_driver_sql(
                "SELECT concurrency_version FROM projects WHERE id = ?",
                (str(owner.project.id),),
            ).scalar_one()

    assert counts == {
        "outlines": 1,
        "outline_revisions": 2,
        "outline_heads": 1,
        "volumes": 2,
        "volume_revisions": 3,
        "volume_heads": 2,
        "chapters": 2,
        "chapter_revisions": 3,
        "chapter_heads": 2,
    }
    assert owner_version == 1


def test_real_repository_application_conflicts_and_ownership(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        first = create_project(database)
        second = database.project_repository.create(project_aggregate(2))
        service = NovelStructureCommandService(
            database.repository,
            database.project_repository,
            lambda: BASE_TIME,
            _factories([outline_id(111), outline_id(112)]),
            _factories([outline_revision_id(11_101), outline_revision_id(11_102)]),
            _factories([volume_id(211), volume_id(212), volume_id(213), volume_id(214)]),
            _factories(
                [
                    volume_revision_id(11_201),
                    volume_revision_id(11_202),
                    volume_revision_id(11_203),
                    volume_revision_id(11_204),
                ]
            ),
            _factories([chapter_id(311), chapter_id(312), chapter_id(313)]),
            _factories(
                [
                    chapter_revision_id(11_301),
                    chapter_revision_id(11_302),
                    chapter_revision_id(11_303),
                ]
            ),
        )
        service.create_outline(CreateOutlineCommand(str(first.project.id), "Outline", ""))
        with pytest.raises(OutlineAlreadyExists):
            service.create_outline(CreateOutlineCommand(str(first.project.id), "Second", ""))

        volume = service.create_volume(CreateVolumeCommand(str(first.project.id), "Volume", "", 1))
        with pytest.raises(VolumePositionConflict):
            service.create_volume(
                CreateVolumeCommand(str(first.project.id), "Duplicate position", "", 1)
            )
        movable_volume = service.create_volume(
            CreateVolumeCommand(str(first.project.id), "Movable volume", "", 2)
        )
        other_volume = service.create_volume(
            CreateVolumeCommand(str(second.project.id), "Other volume", "", 1)
        )
        service.create_chapter(
            CreateChapterCommand(str(first.project.id), volume.volume_id, "Chapter", "", 1)
        )
        with pytest.raises(ChapterPositionConflict):
            service.create_chapter(
                CreateChapterCommand(str(first.project.id), volume.volume_id, "Duplicate", "", 1)
            )
        movable_chapter = service.create_chapter(
            CreateChapterCommand(str(first.project.id), volume.volume_id, "Movable chapter", "", 2)
        )
        with pytest.raises(VolumePositionConflict):
            service.update_volume(
                UpdateVolumeCommand(movable_volume.volume_id, 1, "Conflict", "", 1)
            )
        with pytest.raises(ChapterPositionConflict):
            service.update_chapter(
                UpdateChapterCommand(movable_chapter.chapter_id, 1, "Conflict", "", 1)
            )
        with pytest.raises(ChapterVolumeOwnershipMismatch):
            service.create_chapter(
                CreateChapterCommand(
                    str(first.project.id), other_volume.volume_id, "Mismatch", "", 2
                )
            )
        with pytest.raises(VolumeNotFound):
            service.create_chapter(
                CreateChapterCommand(str(first.project.id), str(volume_id(999)), "Missing", "", 2)
            )
        with pytest.raises(ProjectNotFound):
            service.create_volume(
                CreateVolumeCommand(str(project_id(999)), "Missing project", "", 1)
            )
