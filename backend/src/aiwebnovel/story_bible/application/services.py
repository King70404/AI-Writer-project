"""Story Bible application services over the public repository contract."""

from collections.abc import Callable

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)
from aiwebnovel.story_bible.application.errors import (
    StoryBibleForProjectNotFound,
)
from aiwebnovel.story_bible.application.mappers import (
    story_bible_snapshot_from_aggregate,
)
from aiwebnovel.story_bible.application.models import StoryBibleSnapshot
from aiwebnovel.story_bible.application.queries import (
    GetStoryBibleForProjectQuery,
    GetStoryBibleQuery,
)
from aiwebnovel.story_bible.errors import StoryBibleNotFound
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.repository import StoryBibleRepository
from aiwebnovel.story_bible.transitions import create_initial_story_bible
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

StoryBibleIdFactory = Callable[[], StoryBibleId]
StoryBibleRevisionIdFactory = Callable[[], StoryBibleRevisionId]


def _story_bible_id_from_factory(factory: StoryBibleIdFactory) -> StoryBibleId:
    identifier = factory()
    if type(identifier) is not StoryBibleId:
        raise TypeError("story_bible_id_factory must return a StoryBibleId")
    return identifier


def _revision_id_from_factory(
    factory: StoryBibleRevisionIdFactory,
) -> StoryBibleRevisionId:
    identifier = factory()
    if type(identifier) is not StoryBibleRevisionId:
        raise TypeError("revision_id_factory must return a StoryBibleRevisionId")
    return identifier


class StoryBibleCommandService:
    """Execute one atomic repository write for each Story Bible command."""

    def __init__(
        self,
        repository: StoryBibleRepository,
        clock: Clock,
        story_bible_id_factory: StoryBibleIdFactory,
        revision_id_factory: StoryBibleRevisionIdFactory,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._story_bible_id_factory = story_bible_id_factory
        self._revision_id_factory = revision_id_factory

    def create_story_bible(
        self,
        command: CreateStoryBibleCommand,
    ) -> StoryBibleSnapshot:
        if type(command) is not CreateStoryBibleCommand:
            raise TypeError("command must be a CreateStoryBibleCommand")
        project_id = ProjectId.parse(command.project_id)
        title = StoryBibleTitle(command.title)
        content = StoryBibleContent(command.content)
        now = self._clock()
        story_bible_id = _story_bible_id_from_factory(
            self._story_bible_id_factory,
        )
        revision_id = _revision_id_from_factory(self._revision_id_factory)
        aggregate = create_initial_story_bible(
            story_bible_id=story_bible_id,
            revision_id=revision_id,
            project_id=project_id,
            title=title,
            content=content,
            now=now,
        )
        created = self._repository.create(aggregate)
        return story_bible_snapshot_from_aggregate(created)

    def revise_story_bible(
        self,
        command: ReviseStoryBibleCommand,
    ) -> StoryBibleSnapshot:
        if type(command) is not ReviseStoryBibleCommand:
            raise TypeError("command must be a ReviseStoryBibleCommand")
        story_bible_id = StoryBibleId.parse(command.story_bible_id)
        expected_version = ConcurrencyVersion(command.expected_version)
        title = StoryBibleTitle(command.title)
        content = StoryBibleContent(command.content)
        revised = self._repository.append_revision(
            story_bible_id,
            expected_version=expected_version,
            title=title,
            content=content,
            clock=self._clock,
            revision_id_factory=self._revision_id_factory,
        )
        return story_bible_snapshot_from_aggregate(revised)


class StoryBibleQueryService:
    """Read detached current Story Bible snapshots without side effects."""

    def __init__(
        self,
        repository: StoryBibleRepository,
    ) -> None:
        self._repository = repository

    def get_story_bible(
        self,
        query: GetStoryBibleQuery,
    ) -> StoryBibleSnapshot:
        if type(query) is not GetStoryBibleQuery:
            raise TypeError("query must be a GetStoryBibleQuery")
        story_bible_id = StoryBibleId.parse(query.story_bible_id)
        aggregate = self._repository.get(story_bible_id)
        if aggregate is None:
            raise StoryBibleNotFound(story_bible_id)
        return story_bible_snapshot_from_aggregate(aggregate)

    def get_story_bible_for_project(
        self,
        query: GetStoryBibleForProjectQuery,
    ) -> StoryBibleSnapshot:
        if type(query) is not GetStoryBibleForProjectQuery:
            raise TypeError("query must be a GetStoryBibleForProjectQuery")
        project_id = ProjectId.parse(query.project_id)
        aggregate = self._repository.get_for_project(project_id)
        if aggregate is None:
            raise StoryBibleForProjectNotFound(project_id)
        return story_bible_snapshot_from_aggregate(aggregate)


__all__ = ["StoryBibleCommandService", "StoryBibleQueryService"]
