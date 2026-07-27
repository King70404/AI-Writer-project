"""Small spies for Story Bible application tests; never imported by production."""

from __future__ import annotations

from collections.abc import Callable

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.entities import StoryBibleAggregate
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle


class SpyStoryBibleRepository:
    """Configurable contract spy with exact call recording."""

    def __init__(
        self,
        *,
        create_result: StoryBibleAggregate | None = None,
        get_result: StoryBibleAggregate | None = None,
        get_for_project_result: StoryBibleAggregate | None = None,
        append_result: StoryBibleAggregate | None = None,
        create_error: Exception | None = None,
        get_error: Exception | None = None,
        get_for_project_error: Exception | None = None,
        append_error: Exception | None = None,
    ) -> None:
        self.create_result = create_result
        self.get_result = get_result
        self.get_for_project_result = get_for_project_result
        self.append_result = append_result
        self.create_error = create_error
        self.get_error = get_error
        self.get_for_project_error = get_for_project_error
        self.append_error = append_error
        self.create_calls: list[StoryBibleAggregate] = []
        self.get_calls: list[StoryBibleId] = []
        self.get_for_project_calls: list[ProjectId] = []
        self.append_calls: list[
            tuple[
                StoryBibleId,
                ConcurrencyVersion,
                StoryBibleTitle,
                StoryBibleContent,
                Clock,
                Callable[[], StoryBibleRevisionId],
            ]
        ] = []

    def create(self, aggregate: StoryBibleAggregate) -> StoryBibleAggregate:
        self.create_calls.append(aggregate)
        if self.create_error is not None:
            raise self.create_error
        return aggregate if self.create_result is None else self.create_result

    def get(self, story_bible_id: StoryBibleId) -> StoryBibleAggregate | None:
        self.get_calls.append(story_bible_id)
        if self.get_error is not None:
            raise self.get_error
        return self.get_result

    def get_for_project(self, project_id: ProjectId) -> StoryBibleAggregate | None:
        self.get_for_project_calls.append(project_id)
        if self.get_for_project_error is not None:
            raise self.get_for_project_error
        return self.get_for_project_result

    def append_revision(
        self,
        story_bible_id: StoryBibleId,
        *,
        expected_version: ConcurrencyVersion,
        title: StoryBibleTitle,
        content: StoryBibleContent,
        clock: Clock,
        revision_id_factory: Callable[[], StoryBibleRevisionId],
    ) -> StoryBibleAggregate:
        self.append_calls.append(
            (
                story_bible_id,
                expected_version,
                title,
                content,
                clock,
                revision_id_factory,
            )
        )
        if self.append_error is not None:
            raise self.append_error
        if self.append_result is None:
            raise AssertionError("append_result must be configured")
        return self.append_result


__all__ = ["SpyStoryBibleRepository"]
