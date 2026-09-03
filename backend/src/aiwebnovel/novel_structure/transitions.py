"""Pure creation and immutable revision transitions for novel structure."""

from datetime import datetime

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.novel_structure.entities import (
    Chapter,
    ChapterAggregate,
    ChapterHead,
    ChapterRevision,
    Outline,
    OutlineAggregate,
    OutlineHead,
    OutlineRevision,
    Volume,
    VolumeAggregate,
    VolumeHead,
    VolumeRevision,
    assert_chapter_belongs_to_volume,
    normalize_novel_structure_time,
)
from aiwebnovel.novel_structure.errors import InvalidNovelStructureState
from aiwebnovel.novel_structure.identifiers import (
    ChapterId,
    ChapterRevisionId,
    OutlineId,
    OutlineRevisionId,
    VolumeId,
    VolumeRevisionId,
)
from aiwebnovel.novel_structure.values import (
    ManuscriptContent,
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.project.identifiers import ProjectId


def create_initial_outline(
    *,
    outline_id: OutlineId,
    revision_id: OutlineRevisionId,
    project_id: ProjectId,
    title: NovelStructureTitle,
    summary: NovelStructureSummary,
    now: datetime,
) -> OutlineAggregate:
    """Create Outline revision one from caller-supplied domain values."""
    if (
        type(outline_id) is not OutlineId
        or type(revision_id) is not OutlineRevisionId
        or type(project_id) is not ProjectId
        or type(title) is not NovelStructureTitle
        or type(summary) is not NovelStructureSummary
    ):
        raise InvalidNovelStructureState
    normalized_now = normalize_novel_structure_time(now)
    outline = Outline(
        id=outline_id,
        project_id=project_id,
        concurrency_version=ConcurrencyVersion(),
        created_at=normalized_now,
        updated_at=normalized_now,
    )
    revision = OutlineRevision(
        id=revision_id,
        outline_id=outline_id,
        revision_number=RevisionNumber(),
        title=title,
        summary=summary,
        created_at=normalized_now,
    )
    head = OutlineHead(outline_id=outline_id, revision_id=revision_id, updated_at=normalized_now)
    return OutlineAggregate(outline=outline, head=head, current_revision=revision)


def append_outline_revision(
    aggregate: OutlineAggregate,
    *,
    expected_version: ConcurrencyVersion,
    revision_id: OutlineRevisionId,
    title: NovelStructureTitle,
    summary: NovelStructureSummary,
    now: datetime,
) -> OutlineAggregate:
    """Append one complete Outline revision after a concurrency check."""
    if type(aggregate) is not OutlineAggregate:
        raise InvalidNovelStructureState
    assert_expected_version(actual=aggregate.outline.concurrency_version, expected=expected_version)
    if (
        type(revision_id) is not OutlineRevisionId
        or type(title) is not NovelStructureTitle
        or type(summary) is not NovelStructureSummary
    ):
        raise InvalidNovelStructureState
    normalized_now = normalize_novel_structure_time(now)
    if (
        normalized_now < aggregate.outline.updated_at
        or revision_id == aggregate.current_revision.id
    ):
        raise InvalidNovelStructureState
    outline = Outline(
        id=aggregate.outline.id,
        project_id=aggregate.outline.project_id,
        concurrency_version=aggregate.outline.concurrency_version.next(),
        created_at=aggregate.outline.created_at,
        updated_at=normalized_now,
    )
    revision = OutlineRevision(
        id=revision_id,
        outline_id=outline.id,
        revision_number=aggregate.current_revision.revision_number.next(),
        title=title,
        summary=summary,
        created_at=normalized_now,
    )
    head = OutlineHead(outline_id=outline.id, revision_id=revision_id, updated_at=normalized_now)
    return OutlineAggregate(outline=outline, head=head, current_revision=revision)


def create_initial_volume(
    *,
    volume_id: VolumeId,
    revision_id: VolumeRevisionId,
    project_id: ProjectId,
    title: NovelStructureTitle,
    summary: NovelStructureSummary,
    position: NovelStructurePosition,
    now: datetime,
) -> VolumeAggregate:
    """Create Volume revision one from caller-supplied domain values."""
    if (
        type(volume_id) is not VolumeId
        or type(revision_id) is not VolumeRevisionId
        or type(project_id) is not ProjectId
        or type(title) is not NovelStructureTitle
        or type(summary) is not NovelStructureSummary
        or type(position) is not NovelStructurePosition
    ):
        raise InvalidNovelStructureState
    normalized_now = normalize_novel_structure_time(now)
    volume = Volume(
        id=volume_id,
        project_id=project_id,
        concurrency_version=ConcurrencyVersion(),
        created_at=normalized_now,
        updated_at=normalized_now,
    )
    revision = VolumeRevision(
        id=revision_id,
        volume_id=volume_id,
        revision_number=RevisionNumber(),
        title=title,
        summary=summary,
        position=position,
        created_at=normalized_now,
    )
    head = VolumeHead(volume_id=volume_id, revision_id=revision_id, updated_at=normalized_now)
    return VolumeAggregate(volume=volume, head=head, current_revision=revision)


def append_volume_revision(
    aggregate: VolumeAggregate,
    *,
    expected_version: ConcurrencyVersion,
    revision_id: VolumeRevisionId,
    title: NovelStructureTitle,
    summary: NovelStructureSummary,
    position: NovelStructurePosition,
    now: datetime,
) -> VolumeAggregate:
    """Append one complete Volume revision after a concurrency check."""
    if type(aggregate) is not VolumeAggregate:
        raise InvalidNovelStructureState
    assert_expected_version(actual=aggregate.volume.concurrency_version, expected=expected_version)
    if (
        type(revision_id) is not VolumeRevisionId
        or type(title) is not NovelStructureTitle
        or type(summary) is not NovelStructureSummary
        or type(position) is not NovelStructurePosition
    ):
        raise InvalidNovelStructureState
    normalized_now = normalize_novel_structure_time(now)
    if normalized_now < aggregate.volume.updated_at or revision_id == aggregate.current_revision.id:
        raise InvalidNovelStructureState
    volume = Volume(
        id=aggregate.volume.id,
        project_id=aggregate.volume.project_id,
        concurrency_version=aggregate.volume.concurrency_version.next(),
        created_at=aggregate.volume.created_at,
        updated_at=normalized_now,
    )
    revision = VolumeRevision(
        id=revision_id,
        volume_id=volume.id,
        revision_number=aggregate.current_revision.revision_number.next(),
        title=title,
        summary=summary,
        position=position,
        created_at=normalized_now,
    )
    head = VolumeHead(volume_id=volume.id, revision_id=revision_id, updated_at=normalized_now)
    return VolumeAggregate(volume=volume, head=head, current_revision=revision)


def create_initial_chapter(
    *,
    chapter_id: ChapterId,
    revision_id: ChapterRevisionId,
    project_id: ProjectId,
    volume: Volume,
    title: NovelStructureTitle,
    summary: NovelStructureSummary,
    position: NovelStructurePosition,
    now: datetime,
) -> ChapterAggregate:
    """Create Chapter revision one and enforce Volume/Project ownership."""
    if (
        type(chapter_id) is not ChapterId
        or type(revision_id) is not ChapterRevisionId
        or type(project_id) is not ProjectId
        or type(volume) is not Volume
        or type(title) is not NovelStructureTitle
        or type(summary) is not NovelStructureSummary
        or type(position) is not NovelStructurePosition
        or volume.project_id != project_id
    ):
        raise InvalidNovelStructureState
    normalized_now = normalize_novel_structure_time(now)
    chapter = Chapter(
        id=chapter_id,
        project_id=project_id,
        volume_id=volume.id,
        concurrency_version=ConcurrencyVersion(),
        created_at=normalized_now,
        updated_at=normalized_now,
    )
    assert_chapter_belongs_to_volume(chapter, volume)
    revision = ChapterRevision(
        id=revision_id,
        chapter_id=chapter_id,
        revision_number=RevisionNumber(),
        title=title,
        summary=summary,
        position=position,
        created_at=normalized_now,
    )
    head = ChapterHead(chapter_id=chapter_id, revision_id=revision_id, updated_at=normalized_now)
    return ChapterAggregate(chapter=chapter, head=head, current_revision=revision)


def append_chapter_revision(
    aggregate: ChapterAggregate,
    *,
    expected_version: ConcurrencyVersion,
    revision_id: ChapterRevisionId,
    title: NovelStructureTitle,
    summary: NovelStructureSummary,
    position: NovelStructurePosition,
    now: datetime,
) -> ChapterAggregate:
    """Append one Chapter structure revision while preserving manuscript prose."""
    if type(aggregate) is not ChapterAggregate:
        raise InvalidNovelStructureState
    return _append_chapter_revision(
        aggregate,
        expected_version=expected_version,
        revision_id=revision_id,
        title=title,
        summary=summary,
        position=position,
        content=aggregate.current_revision.content,
        now=now,
    )


def append_chapter_content_revision(
    aggregate: ChapterAggregate,
    *,
    expected_version: ConcurrencyVersion,
    revision_id: ChapterRevisionId,
    content: ManuscriptContent,
    now: datetime,
) -> ChapterAggregate:
    """Append one manuscript revision while preserving Chapter structure."""
    if type(aggregate) is not ChapterAggregate:
        raise InvalidNovelStructureState
    return _append_chapter_revision(
        aggregate,
        expected_version=expected_version,
        revision_id=revision_id,
        title=aggregate.current_revision.title,
        summary=aggregate.current_revision.summary,
        position=aggregate.current_revision.position,
        content=content,
        now=now,
    )


def _append_chapter_revision(
    aggregate: ChapterAggregate,
    *,
    expected_version: ConcurrencyVersion,
    revision_id: ChapterRevisionId,
    title: NovelStructureTitle,
    summary: NovelStructureSummary,
    position: NovelStructurePosition,
    content: ManuscriptContent,
    now: datetime,
) -> ChapterAggregate:
    """Build a complete immutable Chapter revision from validated domain values."""
    assert_expected_version(actual=aggregate.chapter.concurrency_version, expected=expected_version)
    if (
        type(revision_id) is not ChapterRevisionId
        or type(title) is not NovelStructureTitle
        or type(summary) is not NovelStructureSummary
        or type(position) is not NovelStructurePosition
        or type(content) is not ManuscriptContent
    ):
        raise InvalidNovelStructureState
    normalized_now = normalize_novel_structure_time(now)
    if (
        normalized_now < aggregate.chapter.updated_at
        or revision_id == aggregate.current_revision.id
    ):
        raise InvalidNovelStructureState
    chapter = Chapter(
        id=aggregate.chapter.id,
        project_id=aggregate.chapter.project_id,
        volume_id=aggregate.chapter.volume_id,
        concurrency_version=aggregate.chapter.concurrency_version.next(),
        created_at=aggregate.chapter.created_at,
        updated_at=normalized_now,
    )
    revision = ChapterRevision(
        id=revision_id,
        chapter_id=chapter.id,
        revision_number=aggregate.current_revision.revision_number.next(),
        title=title,
        summary=summary,
        position=position,
        created_at=normalized_now,
        content=content,
    )
    head = ChapterHead(chapter_id=chapter.id, revision_id=revision_id, updated_at=normalized_now)
    return ChapterAggregate(chapter=chapter, head=head, current_revision=revision)
