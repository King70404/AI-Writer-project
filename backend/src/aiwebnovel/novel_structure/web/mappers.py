"""Explicit novel-structure HTTP/application mappings."""

from aiwebnovel.novel_structure.application.commands import (
    CreateChapterCommand,
    CreateOutlineCommand,
    CreateVolumeCommand,
    UpdateChapterCommand,
    UpdateOutlineCommand,
    UpdateVolumeCommand,
)
from aiwebnovel.novel_structure.application.models import (
    ChapterSnapshot,
    OutlineSnapshot,
    VolumeSnapshot,
)
from aiwebnovel.novel_structure.web.dto import (
    ChapterResponse,
    CreateChapterRequest,
    CreateOutlineRequest,
    CreateVolumeRequest,
    OutlineResponse,
    UpdateChapterRequest,
    UpdateOutlineRequest,
    UpdateVolumeRequest,
    VolumeResponse,
)


def _require_exact(value: object, expected: type[object], message: str) -> None:
    if type(value) is not expected:
        raise TypeError(message)


def create_outline_command(project_id: str, request: CreateOutlineRequest) -> CreateOutlineCommand:
    _require_exact(project_id, str, "project_id must be a string")
    _require_exact(request, CreateOutlineRequest, "request must be a CreateOutlineRequest")
    return CreateOutlineCommand(project_id=project_id, title=request.title, summary=request.summary)


def update_outline_command(
    outline_id: str, expected_version: int, request: UpdateOutlineRequest
) -> UpdateOutlineCommand:
    _require_exact(outline_id, str, "outline_id must be a string")
    _require_exact(expected_version, int, "expected_version must be an integer")
    _require_exact(request, UpdateOutlineRequest, "request must be an UpdateOutlineRequest")
    return UpdateOutlineCommand(
        outline_id=outline_id,
        expected_version=expected_version,
        title=request.title,
        summary=request.summary,
    )


def create_volume_command(project_id: str, request: CreateVolumeRequest) -> CreateVolumeCommand:
    _require_exact(project_id, str, "project_id must be a string")
    _require_exact(request, CreateVolumeRequest, "request must be a CreateVolumeRequest")
    return CreateVolumeCommand(
        project_id=project_id,
        title=request.title,
        summary=request.summary,
        position=request.position,
    )


def update_volume_command(
    volume_id: str, expected_version: int, request: UpdateVolumeRequest
) -> UpdateVolumeCommand:
    _require_exact(volume_id, str, "volume_id must be a string")
    _require_exact(expected_version, int, "expected_version must be an integer")
    _require_exact(request, UpdateVolumeRequest, "request must be an UpdateVolumeRequest")
    return UpdateVolumeCommand(
        volume_id=volume_id,
        expected_version=expected_version,
        title=request.title,
        summary=request.summary,
        position=request.position,
    )


def create_chapter_command(
    project_id: str, volume_id: str, request: CreateChapterRequest
) -> CreateChapterCommand:
    _require_exact(project_id, str, "project_id must be a string")
    _require_exact(volume_id, str, "volume_id must be a string")
    _require_exact(request, CreateChapterRequest, "request must be a CreateChapterRequest")
    return CreateChapterCommand(
        project_id=project_id,
        volume_id=volume_id,
        title=request.title,
        summary=request.summary,
        position=request.position,
    )


def update_chapter_command(
    chapter_id: str, expected_version: int, request: UpdateChapterRequest
) -> UpdateChapterCommand:
    _require_exact(chapter_id, str, "chapter_id must be a string")
    _require_exact(expected_version, int, "expected_version must be an integer")
    _require_exact(request, UpdateChapterRequest, "request must be an UpdateChapterRequest")
    return UpdateChapterCommand(
        chapter_id=chapter_id,
        expected_version=expected_version,
        title=request.title,
        summary=request.summary,
        position=request.position,
    )


def outline_response(snapshot: OutlineSnapshot) -> OutlineResponse:
    if type(snapshot) is not OutlineSnapshot:
        raise TypeError("snapshot must be an OutlineSnapshot")
    return OutlineResponse(
        outline_id=snapshot.outline_id,
        project_id=snapshot.project_id,
        current_revision_id=snapshot.current_revision_id,
        revision_number=snapshot.revision_number,
        concurrency_version=snapshot.concurrency_version,
        title=snapshot.title,
        summary=snapshot.summary,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        revision_created_at=snapshot.revision_created_at,
    )


def volume_response(snapshot: VolumeSnapshot) -> VolumeResponse:
    if type(snapshot) is not VolumeSnapshot:
        raise TypeError("snapshot must be a VolumeSnapshot")
    return VolumeResponse(
        volume_id=snapshot.volume_id,
        project_id=snapshot.project_id,
        current_revision_id=snapshot.current_revision_id,
        revision_number=snapshot.revision_number,
        concurrency_version=snapshot.concurrency_version,
        title=snapshot.title,
        summary=snapshot.summary,
        position=snapshot.position,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        revision_created_at=snapshot.revision_created_at,
    )


def chapter_response(snapshot: ChapterSnapshot) -> ChapterResponse:
    if type(snapshot) is not ChapterSnapshot:
        raise TypeError("snapshot must be a ChapterSnapshot")
    return ChapterResponse(
        chapter_id=snapshot.chapter_id,
        project_id=snapshot.project_id,
        volume_id=snapshot.volume_id,
        current_revision_id=snapshot.current_revision_id,
        revision_number=snapshot.revision_number,
        concurrency_version=snapshot.concurrency_version,
        title=snapshot.title,
        summary=snapshot.summary,
        position=snapshot.position,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        revision_created_at=snapshot.revision_created_at,
    )


__all__ = [
    "chapter_response",
    "create_chapter_command",
    "create_outline_command",
    "create_volume_command",
    "outline_response",
    "update_chapter_command",
    "update_outline_command",
    "update_volume_command",
    "volume_response",
]
