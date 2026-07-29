"""Character entity and aggregate invariants."""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import timedelta, timezone

import pytest
from tests.backend.character_support import (
    BASE_TIME,
    character_id,
    initial_aggregate,
    project_id,
    revision_id,
)

from aiwebnovel.character import (
    Character,
    CharacterAggregate,
    CharacterHead,
    CharacterName,
    CharacterProfile,
    CharacterRevision,
    CharacterRole,
    InvalidCharacterState,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber

CANARY = "CHARACTER_SECRET_CANARY"


def test_valid_entities_have_exact_fields_and_normalize_aware_time() -> None:
    aggregate = initial_aggregate()
    local = BASE_TIME.astimezone(timezone(timedelta(hours=8)))
    stable = replace(aggregate.character, created_at=local, updated_at=local)

    assert stable.created_at == BASE_TIME
    assert [item.name for item in fields(Character)] == [
        "id",
        "project_id",
        "concurrency_version",
        "created_at",
        "updated_at",
    ]
    assert [item.name for item in fields(CharacterRevision)] == [
        "id",
        "character_id",
        "revision_number",
        "name",
        "role",
        "profile",
        "created_at",
    ]
    assert [item.name for item in fields(CharacterHead)] == [
        "character_id",
        "revision_id",
        "updated_at",
    ]
    assert [item.name for item in fields(CharacterAggregate)] == [
        "character",
        "head",
        "current_revision",
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"id": revision_id()},
        {"project_id": character_id()},
        {"concurrency_version": RevisionNumber(1)},
        {"created_at": object()},
        {"created_at": BASE_TIME.replace(tzinfo=None)},
        {"updated_at": BASE_TIME.replace(tzinfo=None)},
        {"created_at": BASE_TIME + timedelta(seconds=1)},
    ],
)
def test_character_rejects_invalid_state(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "id": character_id(),
        "project_id": project_id(),
        "concurrency_version": ConcurrencyVersion(1),
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidCharacterState):
        Character(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"id": character_id()},
        {"character_id": revision_id()},
        {"revision_number": ConcurrencyVersion(1)},
        {"name": CharacterRole("wrong")},
        {"role": CharacterName("wrong")},
        {"profile": CharacterRole("wrong")},
        {"created_at": BASE_TIME.replace(tzinfo=None)},
    ],
)
def test_revision_rejects_invalid_state(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "id": revision_id(),
        "character_id": character_id(),
        "revision_number": RevisionNumber(1),
        "name": CharacterName("角色"),
        "role": CharacterRole("主角"),
        "profile": CharacterProfile("正文"),
        "created_at": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidCharacterState):
        CharacterRevision(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"character_id": revision_id()},
        {"revision_id": character_id()},
        {"updated_at": BASE_TIME.replace(tzinfo=None)},
    ],
)
def test_head_rejects_invalid_state(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "character_id": character_id(),
        "revision_id": revision_id(),
        "updated_at": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidCharacterState):
        CharacterHead(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-character-type",
        "wrong-head-type",
        "wrong-revision-type",
        "head-owner",
        "revision-owner",
        "head-pointer",
        "version",
        "head-time",
        "revision-time",
        "revision-before-created",
    ],
)
def test_aggregate_rejects_every_inconsistent_current_state(mutation: str) -> None:
    original = initial_aggregate(name=CANARY, role=CANARY, profile=CANARY)
    stable: object = original.character
    head: object = original.head
    revision: object = original.current_revision
    if mutation == "wrong-character-type":
        stable = object()
    elif mutation == "wrong-head-type":
        head = object()
    elif mutation == "wrong-revision-type":
        revision = object()
    elif mutation == "head-owner":
        head = replace(original.head, character_id=character_id(20))
    elif mutation == "revision-owner":
        revision = replace(original.current_revision, character_id=character_id(20))
    elif mutation == "head-pointer":
        head = replace(original.head, revision_id=revision_id(20))
    elif mutation == "version":
        stable = replace(original.character, concurrency_version=ConcurrencyVersion(2))
    elif mutation == "head-time":
        head = replace(original.head, updated_at=BASE_TIME + timedelta(seconds=1))
    elif mutation == "revision-time":
        revision = replace(
            original.current_revision,
            created_at=BASE_TIME + timedelta(seconds=1),
        )
    elif mutation == "revision-before-created":
        stable = replace(
            original.character,
            created_at=BASE_TIME + timedelta(seconds=1),
            updated_at=BASE_TIME + timedelta(seconds=1),
        )
        head = replace(original.head, updated_at=BASE_TIME + timedelta(seconds=1))

    with pytest.raises(InvalidCharacterState) as caught:
        CharacterAggregate(
            character=stable,  # type: ignore[arg-type]
            head=head,  # type: ignore[arg-type]
            current_revision=revision,  # type: ignore[arg-type]
        )

    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)


def test_all_character_entities_are_frozen() -> None:
    aggregate = initial_aggregate()

    for value, attribute in [
        (aggregate.character, "project_id"),
        (aggregate.current_revision, "profile"),
        (aggregate.head, "revision_id"),
        (aggregate, "current_revision"),
    ]:
        with pytest.raises((FrozenInstanceError, AttributeError)):
            setattr(value, attribute, object())
