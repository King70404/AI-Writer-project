"""Story Bible command-service ordering, strictness, and propagation."""

from datetime import timedelta

import pytest
from tests.backend.story_bible_application_support import (
    SpyStoryBibleRepository,
)
from tests.backend.story_bible_support import (
    BASE_TIME,
    initial_aggregate,
    project_id,
    revision_id,
    story_bible_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import (
    ConcurrencyConflict,
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
)
from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)
from aiwebnovel.story_bible.application.services import StoryBibleCommandService
from aiwebnovel.story_bible.errors import (
    InvalidStoryBibleContent,
    InvalidStoryBibleTitle,
    StoryBibleDataCorruption,
    StoryBibleNotFound,
    StoryBibleRepositoryError,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.transitions import append_story_bible_revision
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

CANARY = "STORY_BIBLE_APPLICATION_SECRET_CANARY"


def test_create_uses_fixed_order_once_and_repository_result_is_authoritative() -> None:
    events: list[str] = []
    authoritative = initial_aggregate(title="Repository title", content="Repository content")

    class RecordingRepository(SpyStoryBibleRepository):
        def create(self, aggregate):  # type: ignore[no-untyped-def]
            events.append("repository")
            return super().create(aggregate)

    repository = RecordingRepository(create_result=authoritative)

    def clock():
        events.append("clock")
        return BASE_TIME

    def story_id_factory():
        events.append("story-id")
        return story_bible_id()

    def revision_id_factory():
        events.append("revision-id")
        return revision_id()

    service = StoryBibleCommandService(
        repository,
        clock,
        story_id_factory,
        revision_id_factory,
    )

    snapshot = service.create_story_bible(
        CreateStoryBibleCommand(
            project_id=str(project_id()),
            title="  Input title  ",
            content="input\r\ncontent",
        )
    )

    assert events == ["clock", "story-id", "revision-id", "repository"]
    assert len(repository.create_calls) == 1
    submitted = repository.create_calls[0]
    assert type(submitted.story_bible.id) is StoryBibleId
    assert type(submitted.current_revision.id) is StoryBibleRevisionId
    assert submitted.story_bible.project_id == project_id()
    assert str(submitted.current_revision.title) == "Input title"
    assert str(submitted.current_revision.content) == "input\ncontent"
    assert snapshot.title == "Repository title"
    assert snapshot.content == "Repository content"
    assert repository.get_calls == []
    assert repository.get_for_project_calls == []


@pytest.mark.parametrize(
    ("command", "error_type"),
    [
        (object(), TypeError),
        (
            CreateStoryBibleCommand("invalid", "title", "content"),
            InvalidDomainIdentifier,
        ),
        (
            CreateStoryBibleCommand(str(project_id()), f"\x00{CANARY}", "content"),
            InvalidStoryBibleTitle,
        ),
        (
            CreateStoryBibleCommand(str(project_id()), "title", f"\x00{CANARY}"),
            InvalidStoryBibleContent,
        ),
    ],
)
def test_create_invalid_input_has_no_external_side_effects(
    command: object,
    error_type: type[Exception],
) -> None:
    calls: list[str] = []
    repository = SpyStoryBibleRepository()
    service = StoryBibleCommandService(
        repository,
        lambda: calls.append("clock") or BASE_TIME,
        lambda: calls.append("story-id") or story_bible_id(),
        lambda: calls.append("revision-id") or revision_id(),
    )

    with pytest.raises(error_type) as captured:
        service.create_story_bible(command)  # type: ignore[arg-type]

    assert calls == []
    assert repository.create_calls == []
    assert CANARY not in str(captured.value)


def test_create_clock_failure_stops_both_factories_and_repository() -> None:
    calls: list[str] = []
    failure = RuntimeError("clock failed")
    repository = SpyStoryBibleRepository()

    def clock():
        calls.append("clock")
        raise failure

    service = StoryBibleCommandService(
        repository,
        clock,
        lambda: calls.append("story-id") or story_bible_id(),
        lambda: calls.append("revision-id") or revision_id(),
    )

    with pytest.raises(RuntimeError) as captured:
        service.create_story_bible(CreateStoryBibleCommand(str(project_id()), "title", "content"))

    assert captured.value is failure
    assert calls == ["clock"]
    assert repository.create_calls == []


def test_create_story_id_failure_stops_revision_factory_and_repository() -> None:
    calls: list[str] = []
    failure = RuntimeError("factory failed")
    repository = SpyStoryBibleRepository()

    def story_id_factory():
        calls.append("story-id")
        raise failure

    service = StoryBibleCommandService(
        repository,
        lambda: calls.append("clock") or BASE_TIME,
        story_id_factory,
        lambda: calls.append("revision-id") or revision_id(),
    )

    with pytest.raises(RuntimeError) as captured:
        service.create_story_bible(CreateStoryBibleCommand(str(project_id()), "title", "content"))

    assert captured.value is failure
    assert calls == ["clock", "story-id"]
    assert repository.create_calls == []


def test_create_revision_id_failure_stops_repository() -> None:
    calls: list[str] = []
    failure = RuntimeError("revision factory failed")
    repository = SpyStoryBibleRepository()

    def revision_id_factory():
        calls.append("revision-id")
        raise failure

    service = StoryBibleCommandService(
        repository,
        lambda: calls.append("clock") or BASE_TIME,
        lambda: calls.append("story-id") or story_bible_id(),
        revision_id_factory,
    )

    with pytest.raises(RuntimeError) as captured:
        service.create_story_bible(CreateStoryBibleCommand(str(project_id()), "title", "content"))

    assert captured.value is failure
    assert calls == ["clock", "story-id", "revision-id"]
    assert repository.create_calls == []


@pytest.mark.parametrize(
    ("story_factory", "revision_factory", "message"),
    [
        (
            lambda: str(story_bible_id()),
            lambda: revision_id(),
            "story_bible_id_factory must return a StoryBibleId",
        ),
        (
            lambda: story_bible_id(),
            lambda: str(revision_id()),
            "revision_id_factory must return a StoryBibleRevisionId",
        ),
        (
            lambda: project_id(),
            lambda: revision_id(),
            "story_bible_id_factory must return a StoryBibleId",
        ),
    ],
)
def test_create_rejects_wrong_factory_result_types_without_repository(
    story_factory,  # type: ignore[no-untyped-def]
    revision_factory,  # type: ignore[no-untyped-def]
    message: str,
) -> None:
    repository = SpyStoryBibleRepository()
    service = StoryBibleCommandService(
        repository,
        lambda: BASE_TIME,
        story_factory,
        revision_factory,
    )

    with pytest.raises(TypeError, match=f"^{message}$"):
        service.create_story_bible(CreateStoryBibleCommand(str(project_id()), "title", CANARY))

    assert repository.create_calls == []


def test_create_repository_error_is_propagated_without_retry() -> None:
    failure = StoryBibleRepositoryError()
    repository = SpyStoryBibleRepository(create_error=failure)
    service = StoryBibleCommandService(
        repository,
        lambda: BASE_TIME,
        story_bible_id,
        revision_id,
    )

    with pytest.raises(StoryBibleRepositoryError) as captured:
        service.create_story_bible(CreateStoryBibleCommand(str(project_id()), "title", "content"))

    assert captured.value is failure
    assert len(repository.create_calls) == 1


def revised_aggregate():
    aggregate = initial_aggregate()
    return append_story_bible_revision(
        aggregate,
        expected_version=ConcurrencyVersion(1),
        revision_id=revision_id(9),
        title=StoryBibleTitle("Repository revision"),
        content=StoryBibleContent("repository content"),
        now=BASE_TIME + timedelta(seconds=1),
    )


def test_revise_validates_then_passes_injected_dependencies_without_calling_them() -> None:
    calls: list[str] = []
    repository = SpyStoryBibleRepository(append_result=revised_aggregate())

    def clock():
        calls.append("clock")
        return BASE_TIME + timedelta(seconds=1)

    def revision_factory():
        calls.append("revision-id")
        return revision_id(9)

    service = StoryBibleCommandService(
        repository,
        clock,
        story_bible_id,
        revision_factory,
    )

    snapshot = service.revise_story_bible(
        ReviseStoryBibleCommand(
            story_bible_id=str(story_bible_id()),
            expected_version=1,
            title="  Replacement  ",
            content="",
        )
    )

    assert calls == []
    assert len(repository.append_calls) == 1
    (
        submitted_id,
        expected,
        title,
        content,
        submitted_clock,
        submitted_factory,
    ) = repository.append_calls[0]
    assert submitted_id == story_bible_id()
    assert int(expected) == 1
    assert str(title) == "Replacement"
    assert str(content) == ""
    assert submitted_clock is clock
    assert submitted_factory is revision_factory
    assert repository.get_calls == []
    assert repository.get_for_project_calls == []
    assert snapshot.title == "Repository revision"
    assert snapshot.content == "repository content"


@pytest.mark.parametrize(
    ("command", "error_type"),
    [
        (object(), TypeError),
        (ReviseStoryBibleCommand("invalid", 1, "title", "content"), InvalidDomainIdentifier),
        (
            ReviseStoryBibleCommand(str(story_bible_id()), True, "title", "content"),
            InvalidConcurrencyVersion,
        ),
        (
            ReviseStoryBibleCommand(str(story_bible_id()), 0, "title", "content"),
            InvalidConcurrencyVersion,
        ),
        (
            ReviseStoryBibleCommand(str(story_bible_id()), 1, "\x00", "content"),
            InvalidStoryBibleTitle,
        ),
        (
            ReviseStoryBibleCommand(str(story_bible_id()), 1, "title", "\x00"),
            InvalidStoryBibleContent,
        ),
    ],
)
def test_revise_invalid_input_never_calls_repository(
    command: object,
    error_type: type[Exception],
) -> None:
    repository = SpyStoryBibleRepository(append_result=revised_aggregate())
    service = StoryBibleCommandService(
        repository,
        lambda: BASE_TIME,
        story_bible_id,
        revision_id,
    )

    with pytest.raises(error_type):
        service.revise_story_bible(command)  # type: ignore[arg-type]

    assert repository.append_calls == []


@pytest.mark.parametrize(
    "failure",
    [
        ConcurrencyConflict(expected_version=1, actual_version=2),
        StoryBibleNotFound(story_bible_id()),
        StoryBibleDataCorruption(),
        StoryBibleRepositoryError(),
    ],
)
def test_revise_errors_are_propagated_exactly_once_without_retry(
    failure: Exception,
) -> None:
    repository = SpyStoryBibleRepository(append_error=failure)
    service = StoryBibleCommandService(
        repository,
        lambda: BASE_TIME,
        story_bible_id,
        revision_id,
    )

    with pytest.raises(type(failure)) as captured:
        service.revise_story_bible(
            ReviseStoryBibleCommand(
                str(story_bible_id()),
                1,
                "title",
                CANARY,
            )
        )

    assert captured.value is failure
    assert len(repository.append_calls) == 1
    assert CANARY not in str(captured.value)
    if isinstance(failure, ConcurrencyConflict):
        assert failure.expected_version == 1
        assert failure.actual_version == 2
