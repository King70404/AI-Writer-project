"""Pure application orchestration over novel-structure repository contracts."""

from collections.abc import Callable

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
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
    ChapterNotFound,
    ChapterVolumeOwnershipMismatch,
    OutlineNotFound,
    VolumeNotFound,
)
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.novel_structure.repository import NovelStructureRepository
from aiwebnovel.novel_structure.transitions import (
    create_initial_chapter,
    create_initial_outline,
    create_initial_volume,
)
from aiwebnovel.novel_structure.values import (
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.errors import ProjectNotFound
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.repository import ProjectRepository


def _identifier_from_factory[
    IdentifierT: (
        OutlineId,
        OutlineRevisionId,
        VolumeId,
        VolumeRevisionId,
        ChapterId,
        ChapterRevisionId,
    )
](
    factory: Callable[[], IdentifierT],
    expected_type: type[IdentifierT],
    message: str,
) -> IdentifierT:
    identifier = factory()
    if type(identifier) is not expected_type:
        raise TypeError(message)
    return identifier


class NovelStructureCommandService:
    """Execute atomic Outline, Volume, and Chapter writes."""

    def __init__(
        self,
        repository: NovelStructureRepository,
        project_repository: ProjectRepository,
        clock: Clock,
        outline_id_factory: Callable[[], OutlineId],
        outline_revision_id_factory: Callable[[], OutlineRevisionId],
        volume_id_factory: Callable[[], VolumeId],
        volume_revision_id_factory: Callable[[], VolumeRevisionId],
        chapter_id_factory: Callable[[], ChapterId],
        chapter_revision_id_factory: Callable[[], ChapterRevisionId],
    ) -> None:
        self._repository = repository
        self._project_repository = project_repository
        self._clock = clock
        self._outline_id_factory = outline_id_factory
        self._outline_revision_id_factory = outline_revision_id_factory
        self._volume_id_factory = volume_id_factory
        self._volume_revision_id_factory = volume_revision_id_factory
        self._chapter_id_factory = chapter_id_factory
        self._chapter_revision_id_factory = chapter_revision_id_factory

    def _require_project(self, project_id: ProjectId) -> None:
        if self._project_repository.get(project_id) is None:
            raise ProjectNotFound(project_id)

    def create_outline(self, command: CreateOutlineCommand) -> OutlineSnapshot:
        if type(command) is not CreateOutlineCommand:
            raise TypeError("command must be a CreateOutlineCommand")
        project_id = ProjectId.parse(command.project_id)
        title = NovelStructureTitle(command.title)
        summary = NovelStructureSummary(command.summary)
        self._require_project(project_id)
        now = self._clock()
        outline_id = _identifier_from_factory(
            self._outline_id_factory,
            OutlineId,
            "outline_id_factory must return an OutlineId",
        )
        revision_id = _identifier_from_factory(
            self._outline_revision_id_factory,
            OutlineRevisionId,
            "outline_revision_id_factory must return an OutlineRevisionId",
        )
        aggregate = create_initial_outline(
            outline_id=outline_id,
            revision_id=revision_id,
            project_id=project_id,
            title=title,
            summary=summary,
            now=now,
        )
        return outline_snapshot_from_aggregate(self._repository.create_outline(aggregate))

    def update_outline(self, command: UpdateOutlineCommand) -> OutlineSnapshot:
        if type(command) is not UpdateOutlineCommand:
            raise TypeError("command must be an UpdateOutlineCommand")
        outline_id = OutlineId.parse(command.outline_id)
        expected_version = ConcurrencyVersion(command.expected_version)
        title = NovelStructureTitle(command.title)
        summary = NovelStructureSummary(command.summary)
        revised = self._repository.append_outline_revision(
            outline_id,
            expected_version=expected_version,
            title=title,
            summary=summary,
            clock=self._clock,
            revision_id_factory=self._outline_revision_id_factory,
        )
        return outline_snapshot_from_aggregate(revised)

    def create_volume(self, command: CreateVolumeCommand) -> VolumeSnapshot:
        if type(command) is not CreateVolumeCommand:
            raise TypeError("command must be a CreateVolumeCommand")
        project_id = ProjectId.parse(command.project_id)
        title = NovelStructureTitle(command.title)
        summary = NovelStructureSummary(command.summary)
        position = NovelStructurePosition(command.position)
        self._require_project(project_id)
        now = self._clock()
        volume_id = _identifier_from_factory(
            self._volume_id_factory,
            VolumeId,
            "volume_id_factory must return a VolumeId",
        )
        revision_id = _identifier_from_factory(
            self._volume_revision_id_factory,
            VolumeRevisionId,
            "volume_revision_id_factory must return a VolumeRevisionId",
        )
        aggregate = create_initial_volume(
            volume_id=volume_id,
            revision_id=revision_id,
            project_id=project_id,
            title=title,
            summary=summary,
            position=position,
            now=now,
        )
        return volume_snapshot_from_aggregate(self._repository.create_volume(aggregate))

    def update_volume(self, command: UpdateVolumeCommand) -> VolumeSnapshot:
        if type(command) is not UpdateVolumeCommand:
            raise TypeError("command must be an UpdateVolumeCommand")
        volume_id = VolumeId.parse(command.volume_id)
        expected_version = ConcurrencyVersion(command.expected_version)
        title = NovelStructureTitle(command.title)
        summary = NovelStructureSummary(command.summary)
        position = NovelStructurePosition(command.position)
        revised = self._repository.append_volume_revision(
            volume_id,
            expected_version=expected_version,
            title=title,
            summary=summary,
            position=position,
            clock=self._clock,
            revision_id_factory=self._volume_revision_id_factory,
        )
        return volume_snapshot_from_aggregate(revised)

    def create_chapter(self, command: CreateChapterCommand) -> ChapterSnapshot:
        if type(command) is not CreateChapterCommand:
            raise TypeError("command must be a CreateChapterCommand")
        project_id = ProjectId.parse(command.project_id)
        volume_id = VolumeId.parse(command.volume_id)
        title = NovelStructureTitle(command.title)
        summary = NovelStructureSummary(command.summary)
        position = NovelStructurePosition(command.position)
        self._require_project(project_id)
        volume = self._repository.get_volume(volume_id)
        if volume is None:
            raise VolumeNotFound
        if volume.volume.project_id != project_id:
            raise ChapterVolumeOwnershipMismatch
        now = self._clock()
        chapter_id = _identifier_from_factory(
            self._chapter_id_factory,
            ChapterId,
            "chapter_id_factory must return a ChapterId",
        )
        revision_id = _identifier_from_factory(
            self._chapter_revision_id_factory,
            ChapterRevisionId,
            "chapter_revision_id_factory must return a ChapterRevisionId",
        )
        aggregate = create_initial_chapter(
            chapter_id=chapter_id,
            revision_id=revision_id,
            project_id=project_id,
            volume=volume.volume,
            title=title,
            summary=summary,
            position=position,
            now=now,
        )
        return chapter_snapshot_from_aggregate(self._repository.create_chapter(aggregate))

    def update_chapter(self, command: UpdateChapterCommand) -> ChapterSnapshot:
        if type(command) is not UpdateChapterCommand:
            raise TypeError("command must be an UpdateChapterCommand")
        chapter_id = ChapterId.parse(command.chapter_id)
        expected_version = ConcurrencyVersion(command.expected_version)
        title = NovelStructureTitle(command.title)
        summary = NovelStructureSummary(command.summary)
        position = NovelStructurePosition(command.position)
        revised = self._repository.append_chapter_revision(
            chapter_id,
            expected_version=expected_version,
            title=title,
            summary=summary,
            position=position,
            clock=self._clock,
            revision_id_factory=self._chapter_revision_id_factory,
        )
        return chapter_snapshot_from_aggregate(revised)


class NovelStructureQueryService:
    """Read current novel structure without persistence details."""

    def __init__(
        self,
        repository: NovelStructureRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._repository = repository
        self._project_repository = project_repository

    def _require_project(self, project_id: ProjectId) -> None:
        if self._project_repository.get(project_id) is None:
            raise ProjectNotFound(project_id)

    def get_outline(self, query: GetOutlineQuery) -> OutlineSnapshot:
        if type(query) is not GetOutlineQuery:
            raise TypeError("query must be a GetOutlineQuery")
        outline_id = OutlineId.parse(query.outline_id)
        aggregate = self._repository.get_outline(outline_id)
        if aggregate is None:
            raise OutlineNotFound
        return outline_snapshot_from_aggregate(aggregate)

    def get_outline_for_project(
        self,
        query: GetOutlineForProjectQuery,
    ) -> OutlineSnapshot:
        if type(query) is not GetOutlineForProjectQuery:
            raise TypeError("query must be a GetOutlineForProjectQuery")
        project_id = ProjectId.parse(query.project_id)
        self._require_project(project_id)
        aggregate = self._repository.get_outline_for_project(project_id)
        if aggregate is None:
            raise OutlineNotFound
        return outline_snapshot_from_aggregate(aggregate)

    def get_volume(self, query: GetVolumeQuery) -> VolumeSnapshot:
        if type(query) is not GetVolumeQuery:
            raise TypeError("query must be a GetVolumeQuery")
        volume_id = VolumeId.parse(query.volume_id)
        aggregate = self._repository.get_volume(volume_id)
        if aggregate is None:
            raise VolumeNotFound
        return volume_snapshot_from_aggregate(aggregate)

    def list_volumes(self, query: ListVolumesQuery) -> tuple[VolumeSnapshot, ...]:
        if type(query) is not ListVolumesQuery:
            raise TypeError("query must be a ListVolumesQuery")
        project_id = ProjectId.parse(query.project_id)
        self._require_project(project_id)
        snapshots = tuple(
            volume_snapshot_from_aggregate(aggregate)
            for aggregate in self._repository.list_volumes_for_project(project_id)
        )
        return tuple(sorted(snapshots, key=lambda snapshot: snapshot.position))

    def get_chapter(self, query: GetChapterQuery) -> ChapterSnapshot:
        if type(query) is not GetChapterQuery:
            raise TypeError("query must be a GetChapterQuery")
        chapter_id = ChapterId.parse(query.chapter_id)
        aggregate = self._repository.get_chapter(chapter_id)
        if aggregate is None:
            raise ChapterNotFound
        return chapter_snapshot_from_aggregate(aggregate)

    def list_chapters(self, query: ListChaptersQuery) -> tuple[ChapterSnapshot, ...]:
        if type(query) is not ListChaptersQuery:
            raise TypeError("query must be a ListChaptersQuery")
        volume_id = VolumeId.parse(query.volume_id)
        if self._repository.get_volume(volume_id) is None:
            raise VolumeNotFound
        snapshots = tuple(
            chapter_snapshot_from_aggregate(aggregate)
            for aggregate in self._repository.list_chapters_for_volume(volume_id)
        )
        return tuple(sorted(snapshots, key=lambda snapshot: snapshot.position))


__all__ = ["NovelStructureCommandService", "NovelStructureQueryService"]
