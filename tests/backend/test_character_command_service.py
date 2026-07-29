"""Character command-service order, strictness, and error propagation."""

from datetime import timedelta

import pytest
from tests.backend.character_application_support import SpyCharacterRepository
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_aggregate,
    character_id,
    character_revision_id,
    project_id,
)

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.application.services import CharacterCommandService
from aiwebnovel.character.errors import (
    CharacterDataCorruption,
    CharacterNotFound,
    CharacterRepositoryError,
    InvalidCharacterName,
    InvalidCharacterProfile,
    InvalidCharacterRole,
)
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.transitions import append_character_revision
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import (
    ConcurrencyConflict,
    InvalidConcurrencyVersion,
    InvalidDomainIdentifier,
)

CANARY = "CHARACTER_APPLICATION_SECRET_CANARY"


def test_create_fixed_order_once_and_repository_result_is_authoritative() -> None:
    events: list[str] = []
    authoritative = character_aggregate(
        90,
        project_value=1,
        name="Repository Name",
        role="Repository Role",
        profile="repository profile",
    )

    class RecordingRepository(SpyCharacterRepository):
        def create(self, aggregate):  # type: ignore[no-untyped-def]
            events.append("repository")
            return super().create(aggregate)

    repository = RecordingRepository(create_result=authoritative)

    def clock():
        events.append("clock")
        return BASE_TIME

    def character_factory():
        events.append("character-id")
        return character_id(1)

    def revision_factory():
        events.append("revision-id")
        return character_revision_id(20_001)

    service = CharacterCommandService(
        repository,
        clock,
        character_factory,
        revision_factory,
    )
    snapshot = service.create_character(
        CreateCharacterCommand(
            str(project_id(1)),
            "  Input Name  ",
            "  Input Role  ",
            "line one\r\nline two",
        )
    )

    assert events == ["clock", "character-id", "revision-id", "repository"]
    assert len(repository.create_calls) == 1
    submitted = repository.create_calls[0]
    assert type(submitted.character.id) is CharacterId
    assert type(submitted.current_revision.id) is CharacterRevisionId
    assert submitted.character.project_id == project_id(1)
    assert str(submitted.current_revision.name) == "Input Name"
    assert str(submitted.current_revision.role) == "Input Role"
    assert str(submitted.current_revision.profile) == "line one\nline two"
    assert snapshot.name == "Repository Name"
    assert snapshot.profile == "repository profile"
    assert repository.get_calls == []
    assert repository.append_calls == []


@pytest.mark.parametrize(
    ("command", "error_type"),
    [
        (object(), TypeError),
        (
            CreateCharacterCommand("invalid", "Name", "Role", "profile"),
            InvalidDomainIdentifier,
        ),
        (
            CreateCharacterCommand(str(project_id(1)), f"\x00{CANARY}", "Role", "profile"),
            InvalidCharacterName,
        ),
        (
            CreateCharacterCommand(str(project_id(1)), "Name", f"\x00{CANARY}", "profile"),
            InvalidCharacterRole,
        ),
        (
            CreateCharacterCommand(str(project_id(1)), "Name", "Role", f"\x00{CANARY}"),
            InvalidCharacterProfile,
        ),
    ],
)
def test_create_invalid_input_has_no_external_side_effects(
    command: object,
    error_type: type[Exception],
) -> None:
    calls: list[str] = []
    repository = SpyCharacterRepository()
    service = CharacterCommandService(
        repository,
        lambda: calls.append("clock") or BASE_TIME,
        lambda: calls.append("character-id") or character_id(1),
        lambda: calls.append("revision-id") or character_revision_id(20_001),
    )

    with pytest.raises(error_type) as captured:
        service.create_character(command)  # type: ignore[arg-type]

    assert calls == []
    assert repository.create_calls == []
    assert CANARY not in str(captured.value)


@pytest.mark.parametrize("stage", ["clock", "character-id", "revision-id"])
def test_create_failure_stops_later_side_effects(stage: str) -> None:
    events: list[str] = []
    failure = RuntimeError("dependency failed")
    repository = SpyCharacterRepository()

    def clock():
        events.append("clock")
        if stage == "clock":
            raise failure
        return BASE_TIME

    def character_factory():
        events.append("character-id")
        if stage == "character-id":
            raise failure
        return character_id(1)

    def revision_factory():
        events.append("revision-id")
        if stage == "revision-id":
            raise failure
        return character_revision_id(20_001)

    service = CharacterCommandService(
        repository,
        clock,
        character_factory,
        revision_factory,
    )

    with pytest.raises(RuntimeError) as captured:
        service.create_character(
            CreateCharacterCommand(str(project_id(1)), "Name", "Role", "profile")
        )

    expected = {
        "clock": ["clock"],
        "character-id": ["clock", "character-id"],
        "revision-id": ["clock", "character-id", "revision-id"],
    }
    assert captured.value is failure
    assert events == expected[stage]
    assert repository.create_calls == []


class Hostile:
    def __repr__(self) -> str:
        raise AssertionError("repr must not be called")


@pytest.mark.parametrize(
    ("character_factory", "revision_factory", "message"),
    [
        (
            lambda: str(character_id(1)),
            lambda: character_revision_id(20_001),
            "character_id_factory must return a CharacterId",
        ),
        (
            lambda: Hostile(),
            lambda: character_revision_id(20_001),
            "character_id_factory must return a CharacterId",
        ),
        (
            lambda: character_id(1),
            lambda: str(character_revision_id(20_001)),
            "revision_id_factory must return a CharacterRevisionId",
        ),
    ],
)
def test_create_rejects_wrong_factory_types_without_repr_or_repository(
    character_factory,  # type: ignore[no-untyped-def]
    revision_factory,  # type: ignore[no-untyped-def]
    message: str,
) -> None:
    repository = SpyCharacterRepository()
    service = CharacterCommandService(
        repository,
        lambda: BASE_TIME,
        character_factory,
        revision_factory,
    )

    with pytest.raises(TypeError, match=f"^{message}$"):
        service.create_character(CreateCharacterCommand(str(project_id(1)), "Name", "Role", CANARY))

    assert repository.create_calls == []


def test_create_repository_error_is_propagated_once_without_retry() -> None:
    failure = CharacterRepositoryError()
    repository = SpyCharacterRepository(create_error=failure)
    service = CharacterCommandService(
        repository,
        lambda: BASE_TIME,
        lambda: character_id(1),
        lambda: character_revision_id(20_001),
    )

    with pytest.raises(CharacterRepositoryError) as captured:
        service.create_character(
            CreateCharacterCommand(str(project_id(1)), "Name", "Role", "profile")
        )

    assert captured.value is failure
    assert len(repository.create_calls) == 1


def revised_aggregate():
    return append_character_revision(
        character_aggregate(1),
        expected_version=ConcurrencyVersion(1),
        revision_id=character_revision_id(20_002),
        name=CharacterName("Repository Revision"),
        role=CharacterRole("Repository Role"),
        profile=CharacterProfile("repository profile"),
        now=BASE_TIME + timedelta(seconds=1),
    )


def test_revise_passes_dependencies_without_pre_read_or_calling_them() -> None:
    dependency_calls: list[str] = []
    repository = SpyCharacterRepository(append_result=revised_aggregate())

    def clock():
        dependency_calls.append("clock")
        return BASE_TIME + timedelta(seconds=1)

    def revision_factory():
        dependency_calls.append("revision-id")
        return character_revision_id(20_002)

    service = CharacterCommandService(
        repository,
        clock,
        lambda: character_id(999),
        revision_factory,
    )
    snapshot = service.revise_character(
        ReviseCharacterCommand(
            str(character_id(1)),
            1,
            "  Replacement  ",
            "  New Role  ",
            "",
        )
    )

    assert dependency_calls == []
    assert len(repository.append_calls) == 1
    (
        submitted_id,
        expected,
        name,
        role,
        profile,
        submitted_clock,
        submitted_factory,
    ) = repository.append_calls[0]
    assert submitted_id == character_id(1)
    assert int(expected) == 1
    assert str(name) == "Replacement"
    assert str(role) == "New Role"
    assert str(profile) == ""
    assert submitted_clock is clock
    assert submitted_factory is revision_factory
    assert repository.get_calls == []
    assert snapshot.name == "Repository Revision"
    assert snapshot.profile == "repository profile"


@pytest.mark.parametrize(
    ("command", "error_type"),
    [
        (object(), TypeError),
        (
            ReviseCharacterCommand("invalid", 1, "Name", "Role", "profile"),
            InvalidDomainIdentifier,
        ),
        (
            ReviseCharacterCommand(str(character_id(1)), True, "Name", "Role", "profile"),
            InvalidConcurrencyVersion,
        ),
        (
            ReviseCharacterCommand(str(character_id(1)), 0, "Name", "Role", "profile"),
            InvalidConcurrencyVersion,
        ),
        (
            ReviseCharacterCommand(str(character_id(1)), 1, "\x00", "Role", "profile"),
            InvalidCharacterName,
        ),
        (
            ReviseCharacterCommand(str(character_id(1)), 1, "Name", "\x00", "profile"),
            InvalidCharacterRole,
        ),
        (
            ReviseCharacterCommand(str(character_id(1)), 1, "Name", "Role", "\x00"),
            InvalidCharacterProfile,
        ),
    ],
)
def test_revise_invalid_input_never_calls_repository(
    command: object,
    error_type: type[Exception],
) -> None:
    repository = SpyCharacterRepository(append_result=revised_aggregate())
    service = CharacterCommandService(
        repository,
        lambda: BASE_TIME,
        lambda: character_id(1),
        lambda: character_revision_id(20_002),
    )

    with pytest.raises(error_type):
        service.revise_character(command)  # type: ignore[arg-type]

    assert repository.append_calls == []
    assert repository.get_calls == []


@pytest.mark.parametrize(
    "failure",
    [
        ConcurrencyConflict(expected_version=1, actual_version=2),
        CharacterNotFound(character_id(1)),
        CharacterDataCorruption(),
        CharacterRepositoryError(),
    ],
)
def test_revise_errors_propagate_exactly_once_without_retry(
    failure: Exception,
) -> None:
    repository = SpyCharacterRepository(append_error=failure)
    service = CharacterCommandService(
        repository,
        lambda: BASE_TIME,
        lambda: character_id(1),
        lambda: character_revision_id(20_002),
    )

    with pytest.raises(type(failure)) as captured:
        service.revise_character(
            ReviseCharacterCommand(str(character_id(1)), 1, "Name", "Role", CANARY)
        )

    assert captured.value is failure
    assert len(repository.append_calls) == 1
    assert CANARY not in str(captured.value)
    if isinstance(failure, ConcurrencyConflict):
        assert failure.expected_version == 1
        assert failure.actual_version == 2
