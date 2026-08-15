"""Novel-structure application orchestration, strictness, and error propagation."""

from datetime import timedelta
from unittest.mock import Mock

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

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidConcurrencyVersion
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
from aiwebnovel.novel_structure.entities import Volume, VolumeAggregate
from aiwebnovel.novel_structure.errors import (
    ChapterNotFound,
    ChapterVolumeOwnershipMismatch,
    InvalidNovelStructurePosition,
    InvalidNovelStructureSummary,
    InvalidNovelStructureTitle,
    NovelStructureRepositoryError,
    OutlineNotFound,
    VolumeNotFound,
)
from aiwebnovel.novel_structure.repository import NovelStructureRepository
from aiwebnovel.novel_structure.transitions import (
    append_chapter_revision,
    append_outline_revision,
    append_volume_revision,
)
from aiwebnovel.novel_structure.values import (
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.repository import ProjectRepository


def _project_repository(*, exists: bool = True) -> Mock:
    repository = Mock(spec=ProjectRepository)
    repository.get.return_value = Mock() if exists else None
    return repository


def _structure_repository() -> Mock:
    repository = Mock(spec=NovelStructureRepository)
    repository.create_outline.side_effect = lambda aggregate: aggregate
    repository.create_volume.side_effect = lambda aggregate: aggregate
    repository.create_chapter.side_effect = lambda aggregate: aggregate
    return repository


def _command_service(
    repository: Mock,
    project_repository: Mock | None = None,
    *,
    calls: list[str] | None = None,
) -> NovelStructureCommandService:
    events = [] if calls is None else calls
    return NovelStructureCommandService(
        repository,
        _project_repository() if project_repository is None else project_repository,
        lambda: events.append("clock") or BASE_TIME,
        lambda: events.append("outline-id") or outline_id(),
        lambda: events.append("outline-revision-id") or outline_revision_id(),
        lambda: events.append("volume-id") or volume_id(),
        lambda: events.append("volume-revision-id") or volume_revision_id(),
        lambda: events.append("chapter-id") or chapter_id(),
        lambda: events.append("chapter-revision-id") or chapter_revision_id(),
    )


def test_create_outline_validates_project_and_maps_repository_result() -> None:
    calls: list[str] = []
    repository = _structure_repository()
    project_repository = _project_repository()
    authoritative = initial_outline()
    repository.create_outline.return_value = authoritative
    repository.create_outline.side_effect = None
    service = _command_service(repository, project_repository, calls=calls)

    snapshot = service.create_outline(
        CreateOutlineCommand(str(project_id()), "  Total outline  ", "a\r\nsummary")
    )

    project_repository.get.assert_called_once_with(project_id())
    submitted = repository.create_outline.call_args.args[0]
    assert str(submitted.current_revision.title) == "Total outline"
    assert str(submitted.current_revision.summary) == "a\nsummary"
    assert calls == ["clock", "outline-id", "outline-revision-id"]
    assert snapshot.title == "总纲"


@pytest.mark.parametrize(
    "action",
    [
        lambda service: service.create_outline(
            CreateOutlineCommand(str(project_id()), "Title", "")
        ),
        lambda service: service.create_volume(
            CreateVolumeCommand(str(project_id()), "Title", "", 1)
        ),
        lambda service: service.create_chapter(
            CreateChapterCommand(str(project_id()), str(volume_id()), "Title", "", 1)
        ),
    ],
)
def test_create_requires_real_project_before_clock_or_id_factories(action) -> None:  # type: ignore[no-untyped-def]
    calls: list[str] = []
    repository = _structure_repository()
    service = _command_service(
        repository,
        _project_repository(exists=False),
        calls=calls,
    )

    with pytest.raises(ProjectNotFound):
        action(service)

    assert calls == []
    repository.create_outline.assert_not_called()
    repository.create_volume.assert_not_called()
    repository.create_chapter.assert_not_called()


def test_create_volume_and_chapter_use_explicit_positions_and_ownership() -> None:
    repository = _structure_repository()
    project_repository = _project_repository()
    repository.get_volume.return_value = initial_volume()
    service = _command_service(repository, project_repository)

    volume = service.create_volume(CreateVolumeCommand(str(project_id()), " Volume ", "summary", 7))
    chapter = service.create_chapter(
        CreateChapterCommand(str(project_id()), str(volume_id()), " Chapter ", "", 9)
    )

    assert volume.position == 7
    assert chapter.position == 9
    assert chapter.project_id == str(project_id())
    assert chapter.volume_id == str(volume_id())
    repository.get_volume.assert_called_once_with(volume_id())


def test_create_chapter_distinguishes_missing_volume_and_owner_mismatch() -> None:
    repository = _structure_repository()
    service = _command_service(repository)
    repository.get_volume.return_value = None
    command = CreateChapterCommand(str(project_id()), str(volume_id()), "Title", "", 1)

    with pytest.raises(VolumeNotFound):
        service.create_chapter(command)

    other_project_volume = initial_volume()
    repository.get_volume.return_value = VolumeAggregate(
        volume=Volume(
            id=other_project_volume.volume.id,
            project_id=project_id(9),
            concurrency_version=other_project_volume.volume.concurrency_version,
            created_at=other_project_volume.volume.created_at,
            updated_at=other_project_volume.volume.updated_at,
        ),
        head=other_project_volume.head,
        current_revision=other_project_volume.current_revision,
    )
    with pytest.raises(ChapterVolumeOwnershipMismatch):
        service.create_chapter(command)

    repository.create_chapter.assert_not_called()


@pytest.mark.parametrize(
    ("action", "error_type"),
    [
        (lambda service: service.create_outline(object()), TypeError),
        (lambda service: service.create_volume(object()), TypeError),
        (lambda service: service.create_chapter(object()), TypeError),
        (lambda service: service.update_outline(object()), TypeError),
        (lambda service: service.update_volume(object()), TypeError),
        (lambda service: service.update_chapter(object()), TypeError),
        (
            lambda service: service.create_outline(
                CreateOutlineCommand(str(project_id()), "\x00", "")
            ),
            InvalidNovelStructureTitle,
        ),
        (
            lambda service: service.create_volume(
                CreateVolumeCommand(str(project_id()), "Title", "\x00", 1)
            ),
            InvalidNovelStructureSummary,
        ),
        (
            lambda service: service.create_chapter(
                CreateChapterCommand(str(project_id()), str(volume_id()), "Title", "", True)
            ),
            InvalidNovelStructurePosition,
        ),
        (
            lambda service: service.update_outline(
                UpdateOutlineCommand(str(outline_id()), True, "Title", "")
            ),
            InvalidConcurrencyVersion,
        ),
    ],
)
def test_invalid_commands_have_no_write_side_effects(
    action,
    error_type: type[Exception],
) -> None:  # type: ignore[no-untyped-def]
    repository = _structure_repository()
    service = _command_service(repository)

    with pytest.raises(error_type):
        action(service)

    repository.create_outline.assert_not_called()
    repository.create_volume.assert_not_called()
    repository.create_chapter.assert_not_called()
    repository.append_outline_revision.assert_not_called()
    repository.append_volume_revision.assert_not_called()
    repository.append_chapter_revision.assert_not_called()


def test_factory_result_is_strict_and_stops_repository_write() -> None:
    repository = _structure_repository()
    service = NovelStructureCommandService(
        repository,
        _project_repository(),
        lambda: BASE_TIME,
        lambda: "not-an-id",  # type: ignore[arg-type,return-value]
        outline_revision_id,
        volume_id,
        volume_revision_id,
        chapter_id,
        chapter_revision_id,
    )

    with pytest.raises(TypeError, match="outline_id_factory"):
        service.create_outline(CreateOutlineCommand(str(project_id()), "Title", ""))

    repository.create_outline.assert_not_called()


def test_updates_delegate_once_without_pre_reading_or_calling_dependencies() -> None:
    repository = _structure_repository()
    calls: list[str] = []
    service = _command_service(repository, calls=calls)
    revised_outline = append_outline_revision(
        initial_outline(),
        expected_version=ConcurrencyVersion(1),
        revision_id=outline_revision_id(9),
        title=NovelStructureTitle("Outline 2"),
        summary=NovelStructureSummary(""),
        now=BASE_TIME + timedelta(seconds=1),
    )
    revised_volume = append_volume_revision(
        initial_volume(),
        expected_version=ConcurrencyVersion(1),
        revision_id=volume_revision_id(9),
        title=NovelStructureTitle("Volume 2"),
        summary=NovelStructureSummary(""),
        position=NovelStructurePosition(2),
        now=BASE_TIME + timedelta(seconds=1),
    )
    revised_chapter = append_chapter_revision(
        initial_chapter(),
        expected_version=ConcurrencyVersion(1),
        revision_id=chapter_revision_id(9),
        title=NovelStructureTitle("Chapter 2"),
        summary=NovelStructureSummary(""),
        position=NovelStructurePosition(2),
        now=BASE_TIME + timedelta(seconds=1),
    )
    repository.append_outline_revision.return_value = revised_outline
    repository.append_volume_revision.return_value = revised_volume
    repository.append_chapter_revision.return_value = revised_chapter

    outline = service.update_outline(
        UpdateOutlineCommand(str(outline_id()), 1, " Outline input ", "")
    )
    volume = service.update_volume(
        UpdateVolumeCommand(str(volume_id()), 1, " Volume input ", "", 2)
    )
    chapter = service.update_chapter(
        UpdateChapterCommand(str(chapter_id()), 1, " Chapter input ", "", 2)
    )

    assert calls == []
    assert outline.title == "Outline 2"
    assert volume.title == "Volume 2"
    assert chapter.title == "Chapter 2"
    repository.get_outline.assert_not_called()
    repository.get_chapter.assert_not_called()
    assert repository.append_outline_revision.call_count == 1
    assert repository.append_volume_revision.call_count == 1
    assert repository.append_chapter_revision.call_count == 1


@pytest.mark.parametrize(
    "failure",
    [NovelStructureRepositoryError(), ConcurrencyConflict(expected_version=1, actual_version=2)],
)
def test_repository_failure_is_propagated_without_fake_success(failure: Exception) -> None:
    repository = _structure_repository()
    repository.append_outline_revision.side_effect = failure
    service = _command_service(repository)

    with pytest.raises(type(failure)) as captured:
        service.update_outline(
            UpdateOutlineCommand(str(outline_id()), 1, "Title", "secret summary")
        )

    assert captured.value is failure
    assert repository.append_outline_revision.call_count == 1


def test_query_service_gets_current_values_and_orders_lists() -> None:
    repository = _structure_repository()
    project_repository = _project_repository()
    repository.get_outline.return_value = initial_outline()
    repository.get_outline_for_project.return_value = initial_outline()
    repository.get_volume.return_value = initial_volume()
    repository.get_chapter.return_value = initial_chapter()
    volume_two = append_volume_revision(
        initial_volume(),
        expected_version=ConcurrencyVersion(1),
        revision_id=volume_revision_id(9),
        title=NovelStructureTitle("Second"),
        summary=NovelStructureSummary(""),
        position=NovelStructurePosition(2),
        now=BASE_TIME,
    )
    chapter_two = append_chapter_revision(
        initial_chapter(),
        expected_version=ConcurrencyVersion(1),
        revision_id=chapter_revision_id(9),
        title=NovelStructureTitle("Second"),
        summary=NovelStructureSummary(""),
        position=NovelStructurePosition(2),
        now=BASE_TIME,
    )
    repository.list_volumes_for_project.return_value = (volume_two, initial_volume())
    repository.list_chapters_for_volume.return_value = (chapter_two, initial_chapter())
    service = NovelStructureQueryService(repository, project_repository)

    assert service.get_outline(GetOutlineQuery(str(outline_id()))).outline_id == str(outline_id())
    assert service.get_outline_for_project(
        GetOutlineForProjectQuery(str(project_id()))
    ).project_id == str(project_id())
    assert service.get_volume(GetVolumeQuery(str(volume_id()))).volume_id == str(volume_id())
    assert service.get_chapter(GetChapterQuery(str(chapter_id()))).chapter_id == str(chapter_id())
    assert [
        item.position for item in service.list_volumes(ListVolumesQuery(str(project_id())))
    ] == [
        1,
        2,
    ]
    assert [
        item.position for item in service.list_chapters(ListChaptersQuery(str(volume_id())))
    ] == [
        1,
        2,
    ]


@pytest.mark.parametrize(
    ("method", "query", "repository_method", "error_type"),
    [
        ("get_outline", GetOutlineQuery(str(outline_id())), "get_outline", OutlineNotFound),
        ("get_volume", GetVolumeQuery(str(volume_id())), "get_volume", VolumeNotFound),
        ("get_chapter", GetChapterQuery(str(chapter_id())), "get_chapter", ChapterNotFound),
    ],
)
def test_query_by_id_has_precise_not_found(
    method: str,
    query: object,
    repository_method: str,
    error_type: type[Exception],
) -> None:
    repository = _structure_repository()
    getattr(repository, repository_method).return_value = None
    service = NovelStructureQueryService(repository, _project_repository())

    with pytest.raises(error_type):
        getattr(service, method)(query)


def test_project_queries_distinguish_missing_project_from_empty_result() -> None:
    repository = _structure_repository()
    project_repository = _project_repository(exists=False)
    service = NovelStructureQueryService(repository, project_repository)

    with pytest.raises(ProjectNotFound):
        service.get_outline_for_project(GetOutlineForProjectQuery(str(project_id())))
    with pytest.raises(ProjectNotFound):
        service.list_volumes(ListVolumesQuery(str(project_id())))

    project_repository.get.return_value = Mock()
    repository.get_outline_for_project.return_value = None
    repository.list_volumes_for_project.return_value = ()
    with pytest.raises(OutlineNotFound):
        service.get_outline_for_project(GetOutlineForProjectQuery(str(project_id())))
    assert service.list_volumes(ListVolumesQuery(str(project_id()))) == ()


def test_list_chapters_requires_volume_but_allows_empty_list() -> None:
    repository = _structure_repository()
    service = NovelStructureQueryService(repository, _project_repository())
    repository.get_volume.return_value = None
    with pytest.raises(VolumeNotFound):
        service.list_chapters(ListChaptersQuery(str(volume_id())))
    repository.get_volume.return_value = initial_volume()
    repository.list_chapters_for_volume.return_value = ()
    assert service.list_chapters(ListChaptersQuery(str(volume_id()))) == ()


@pytest.mark.parametrize(
    ("method", "query"),
    [
        ("get_outline", object()),
        ("get_outline_for_project", object()),
        ("get_volume", object()),
        ("list_volumes", object()),
        ("get_chapter", object()),
        ("list_chapters", object()),
    ],
)
def test_query_methods_reject_wrong_query_type_without_repository_calls(
    method: str,
    query: object,
) -> None:
    repository = _structure_repository()
    service = NovelStructureQueryService(repository, _project_repository())
    with pytest.raises(TypeError):
        getattr(service, method)(query)
    assert not repository.method_calls
