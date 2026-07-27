"""Explicit mappings between Story Bible HTTP DTOs and application models."""

from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)
from aiwebnovel.story_bible.application.models import StoryBibleSnapshot
from aiwebnovel.story_bible.web.dto import (
    CreateStoryBibleRequest,
    ReviseStoryBibleRequest,
    StoryBibleResponse,
)


def create_story_bible_command_from_request(
    project_id: str,
    request: CreateStoryBibleRequest,
) -> CreateStoryBibleCommand:
    """Map one canonical path ID and strict request to a primitive command."""
    if type(project_id) is not str:
        raise TypeError("project_id must be a string")
    if type(request) is not CreateStoryBibleRequest:
        raise TypeError("request must be a CreateStoryBibleRequest")
    return CreateStoryBibleCommand(
        project_id=project_id,
        title=request.title,
        content=request.content,
    )


def revise_story_bible_command_from_request(
    story_bible_id: str,
    expected_version: int,
    request: ReviseStoryBibleRequest,
) -> ReviseStoryBibleCommand:
    """Map one canonical path ID, ETag version, and complete replacement."""
    if type(story_bible_id) is not str:
        raise TypeError("story_bible_id must be a string")
    if type(expected_version) is not int:
        raise TypeError("expected_version must be an integer")
    if type(request) is not ReviseStoryBibleRequest:
        raise TypeError("request must be a ReviseStoryBibleRequest")
    return ReviseStoryBibleCommand(
        story_bible_id=story_bible_id,
        expected_version=expected_version,
        title=request.title,
        content=request.content,
    )


def story_bible_response_from_snapshot(
    snapshot: StoryBibleSnapshot,
) -> StoryBibleResponse:
    """Copy every public snapshot field into an immutable response DTO."""
    if type(snapshot) is not StoryBibleSnapshot:
        raise TypeError("snapshot must be a StoryBibleSnapshot")
    return StoryBibleResponse(
        story_bible_id=snapshot.story_bible_id,
        project_id=snapshot.project_id,
        current_revision_id=snapshot.current_revision_id,
        revision_number=snapshot.revision_number,
        concurrency_version=snapshot.concurrency_version,
        title=snapshot.title,
        content=snapshot.content,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        revision_created_at=snapshot.revision_created_at,
        head_updated_at=snapshot.head_updated_at,
    )


__all__ = [
    "create_story_bible_command_from_request",
    "revise_story_bible_command_from_request",
    "story_bible_response_from_snapshot",
]
