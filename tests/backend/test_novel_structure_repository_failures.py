"""Failure, validation, and corruption paths for novel-structure persistence."""

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.orm import Session
from tests.backend.novel_structure_repository_support import (
    chapter_aggregate,
    chapter_id,
    create_project,
    later,
    outline_aggregate,
    outline_id,
    outline_revision_id,
    repository_database,
    volume_aggregate,
    volume_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.novel_structure import (
    ChapterAlreadyExists,
    ChapterNotFound,
    InvalidNovelStructureState,
    NovelStructureDataCorruption,
    NovelStructurePosition,
    NovelStructureProjectNotFound,
    NovelStructureRepositoryError,
    NovelStructureSummary,
    NovelStructureTitle,
    OutlineNotFound,
    VolumeAlreadyExists,
    VolumeNotFound,
    append_outline_revision,
)
from aiwebnovel.novel_structure.persistence.repository import (
    SqlAlchemyNovelStructureRepository,
)
from aiwebnovel.project.identifiers import ProjectId

pytestmark = pytest.mark.integration


def _fail() -> None:
    raise RuntimeError("controlled failure")


def test_repository_constructor_and_session_factory_fail_safely() -> None:
    with pytest.raises(TypeError):
        SqlAlchemyNovelStructureRepository(cast(Callable[[], Session], None))

    repository = SqlAlchemyNovelStructureRepository(_fail)
    with pytest.raises(NovelStructureRepositoryError):
        repository.get_outline(outline_id())


def test_empty_reads_and_lists_return_none_or_empty(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        assert database.repository.get_outline(outline_id()) is None
        assert database.repository.get_outline_for_project(ProjectId.new()) is None
        assert database.repository.get_volume(volume_id()) is None
        assert database.repository.list_volumes_for_project(ProjectId.new()) == ()
        assert database.repository.get_chapter(chapter_id()) is None
        assert database.repository.list_chapters_for_volume(volume_id()) == ()


@pytest.mark.parametrize(
    "method_name",
    [
        "get_outline",
        "get_outline_for_project",
        "get_volume",
        "list_volumes_for_project",
        "get_chapter",
        "list_chapters_for_volume",
    ],
)
def test_read_methods_reject_wrong_identifier_types(
    tmp_path: Path,
    method_name: str,
) -> None:
    with repository_database(tmp_path) as database:
        method = getattr(database.repository, method_name)
        with pytest.raises(InvalidNovelStructureState):
            method("not-a-domain-id")


def test_missing_owners_and_duplicate_identities_are_explicit(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        volume = volume_aggregate()
        with pytest.raises(NovelStructureProjectNotFound):
            database.repository.create_volume(volume)
        create_project(database)
        with pytest.raises(VolumeNotFound):
            database.repository.create_chapter(chapter_aggregate(volume))

        database.repository.create_volume(volume)
        with pytest.raises(VolumeAlreadyExists):
            database.repository.create_volume(volume)
        chapter = chapter_aggregate(volume)
        database.repository.create_chapter(chapter)
        with pytest.raises(ChapterAlreadyExists):
            database.repository.create_chapter(chapter)


def test_chapter_missing_project_is_reported_before_volume_lookup(tmp_path: Path) -> None:
    with (
        repository_database(tmp_path) as database,
        pytest.raises(NovelStructureProjectNotFound),
    ):
        database.repository.create_chapter(chapter_aggregate(volume_aggregate()))


def test_append_missing_aggregates_are_explicit(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        common = {
            "expected_version": ConcurrencyVersion(1),
            "title": NovelStructureTitle("Missing"),
            "summary": NovelStructureSummary(),
            "clock": lambda: later(),
        }
        with pytest.raises(OutlineNotFound):
            database.repository.append_outline_revision(
                outline_id(), revision_id_factory=_fail, **common
            )
        with pytest.raises(VolumeNotFound):
            database.repository.append_volume_revision(
                volume_id(),
                position=NovelStructurePosition(1),
                revision_id_factory=_fail,
                **common,
            )
        with pytest.raises(ChapterNotFound):
            database.repository.append_chapter_revision(
                chapter_id(),
                position=NovelStructurePosition(1),
                revision_id_factory=_fail,
                **common,
            )


def test_append_factory_failures_roll_back_and_are_safely_wrapped(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        outline = outline_aggregate()
        volume = volume_aggregate()
        chapter = chapter_aggregate(volume)
        database.repository.create_outline(outline)
        database.repository.create_volume(volume)
        database.repository.create_chapter(chapter)

        with pytest.raises(NovelStructureRepositoryError):
            database.repository.append_outline_revision(
                outline.outline.id,
                expected_version=ConcurrencyVersion(1),
                title=NovelStructureTitle("Next"),
                summary=NovelStructureSummary(),
                clock=lambda: later(),
                revision_id_factory=_fail,
            )
        with pytest.raises(NovelStructureRepositoryError):
            database.repository.append_volume_revision(
                volume.volume.id,
                expected_version=ConcurrencyVersion(1),
                title=NovelStructureTitle("Next"),
                summary=NovelStructureSummary(),
                position=NovelStructurePosition(1),
                clock=lambda: later(),
                revision_id_factory=_fail,
            )
        with pytest.raises(NovelStructureRepositoryError):
            database.repository.append_chapter_revision(
                chapter.chapter.id,
                expected_version=ConcurrencyVersion(1),
                title=NovelStructureTitle("Next"),
                summary=NovelStructureSummary(),
                position=NovelStructurePosition(1),
                clock=lambda: later(),
                revision_id_factory=_fail,
            )

        assert database.repository.get_outline(outline.outline.id) == outline
        assert database.repository.get_volume(volume.volume.id) == volume
        assert database.repository.get_chapter(chapter.chapter.id) == chapter


@pytest.mark.parametrize("owner", ["volume", "chapter"])
def test_mid_create_failures_are_safely_wrapped_and_rolled_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    owner: str,
) -> None:
    with repository_database(tmp_path) as database:
        create_project(database)
        volume = volume_aggregate()
        if owner == "chapter":
            database.repository.create_volume(volume)
            aggregate = chapter_aggregate(volume)
            create = database.repository.create_chapter
        else:
            aggregate = volume
            create = database.repository.create_volume

        monkeypatch.setattr(database.repository, "_insert_three", _fail)
        with pytest.raises(NovelStructureRepositoryError):
            create(aggregate)


def test_read_error_and_corruption_remain_distinct(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database:
        with pytest.raises(NovelStructureDataCorruption):
            database.repository._read_one(
                lambda _session: (_ for _ in ()).throw(NovelStructureDataCorruption)
            )
        with pytest.raises(NovelStructureRepositoryError):
            database.repository._read_one(lambda _session: _fail())

        with pytest.raises(NovelStructureDataCorruption):
            database.repository._outline_from_row((object(), None, None, None))
        with pytest.raises(NovelStructureDataCorruption):
            database.repository._volume_from_row((object(), None, None, None))
        with pytest.raises(NovelStructureDataCorruption):
            database.repository._chapter_from_row((object(), None, None, None, None))


def test_initial_append_and_compare_and_swap_validation() -> None:
    with pytest.raises(InvalidNovelStructureState):
        SqlAlchemyNovelStructureRepository._validate_initial(
            object(), type(outline_aggregate()), "outline"
        )
    revised = append_outline_revision(
        outline_aggregate(),
        expected_version=ConcurrencyVersion(1),
        revision_id=outline_revision_id(20_101),
        title=NovelStructureTitle("Revision 2"),
        summary=NovelStructureSummary(),
        now=later(),
    )
    with pytest.raises(InvalidNovelStructureState):
        SqlAlchemyNovelStructureRepository._validate_initial(revised, type(revised), "outline")
    with pytest.raises(InvalidNovelStructureState):
        SqlAlchemyNovelStructureRepository._validate_append(
            "wrong",
            type(outline_id()),
            ConcurrencyVersion(1),
            NovelStructureTitle("Title"),
            NovelStructureSummary(),
            lambda: later(),
            _fail,
        )
    with pytest.raises(NovelStructureDataCorruption):
        SqlAlchemyNovelStructureRepository._rowcount(SimpleNamespace(rowcount=0))
