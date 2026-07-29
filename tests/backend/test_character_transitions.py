"""Pure Character creation, append, conflict, and sequence tests."""

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
    CharacterName,
    CharacterProfile,
    CharacterRole,
    InvalidCharacterState,
    append_character_revision,
    create_initial_character,
)
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber

CANARY = "CHARACTER_SECRET_CANARY"


def test_initial_creation_uses_supplied_values_and_one_instant() -> None:
    stable_id = character_id()
    new_revision_id = revision_id()
    owner = project_id()
    name = CharacterName("角色")
    role = CharacterRole("导师")
    profile = CharacterProfile("完整角色卡")

    aggregate = create_initial_character(
        character_id=stable_id,
        revision_id=new_revision_id,
        project_id=owner,
        name=name,
        role=role,
        profile=profile,
        now=BASE_TIME,
    )

    assert aggregate.character.id is stable_id
    assert aggregate.character.project_id is owner
    assert aggregate.character.concurrency_version == ConcurrencyVersion(1)
    assert aggregate.character.created_at == BASE_TIME
    assert aggregate.character.updated_at == BASE_TIME
    assert aggregate.current_revision.id is new_revision_id
    assert aggregate.current_revision.revision_number == RevisionNumber(1)
    assert aggregate.current_revision.name is name
    assert aggregate.current_revision.role is role
    assert aggregate.current_revision.profile is profile
    assert aggregate.current_revision.created_at == BASE_TIME
    assert aggregate.head.character_id is stable_id
    assert aggregate.head.revision_id is new_revision_id
    assert aggregate.head.updated_at == BASE_TIME


def test_initial_creation_normalizes_non_utc_aware_time() -> None:
    local_time = BASE_TIME.astimezone(timezone(timedelta(hours=8)))

    aggregate = create_initial_character(
        character_id=character_id(),
        revision_id=revision_id(),
        project_id=project_id(),
        name=CharacterName("角色"),
        role=CharacterRole(),
        profile=CharacterProfile(),
        now=local_time,
    )

    assert aggregate.character.created_at == BASE_TIME
    assert aggregate.current_revision.created_at == BASE_TIME


@pytest.mark.parametrize(
    "changes",
    [
        {"character_id": revision_id()},
        {"revision_id": character_id()},
        {"project_id": character_id()},
        {"name": CharacterRole("wrong")},
        {"role": CharacterName("wrong")},
        {"profile": CharacterRole("wrong")},
        {"now": BASE_TIME.replace(tzinfo=None)},
    ],
)
def test_initial_creation_rejects_invalid_inputs(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "character_id": character_id(),
        "revision_id": revision_id(),
        "project_id": project_id(),
        "name": CharacterName("角色"),
        "role": CharacterRole(),
        "profile": CharacterProfile(),
        "now": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidCharacterState):
        create_initial_character(**arguments)  # type: ignore[arg-type]


def test_append_is_complete_replacement_and_preserves_stable_identity() -> None:
    old = initial_aggregate(name="旧名", role="旧角色", profile="旧正文")
    next_id = revision_id(4)
    now = BASE_TIME + timedelta(seconds=1)

    new = append_character_revision(
        old,
        expected_version=ConcurrencyVersion(1),
        revision_id=next_id,
        name=CharacterName("新名"),
        role=CharacterRole(""),
        profile=CharacterProfile(""),
        now=now,
    )

    assert new is not old
    assert new.character.id is old.character.id
    assert new.character.project_id is old.character.project_id
    assert new.character.created_at == old.character.created_at
    assert new.character.updated_at == now
    assert new.character.concurrency_version == ConcurrencyVersion(2)
    assert new.current_revision.id is next_id
    assert new.current_revision.revision_number == RevisionNumber(2)
    assert str(new.current_revision.name) == "新名"
    assert str(new.current_revision.role) == ""
    assert str(new.current_revision.profile) == ""
    assert new.head.revision_id is next_id
    assert str(old.current_revision.role) == "旧角色"
    assert str(old.current_revision.profile) == "旧正文"


def test_append_allows_equal_time() -> None:
    old = initial_aggregate()

    new = append_character_revision(
        old,
        expected_version=ConcurrencyVersion(1),
        revision_id=revision_id(4),
        name=CharacterName("新名"),
        role=CharacterRole("角色"),
        profile=CharacterProfile("正文"),
        now=old.character.updated_at,
    )

    assert new.character.updated_at == old.character.updated_at


def test_append_rejects_wrong_aggregate_type() -> None:
    with pytest.raises(InvalidCharacterState):
        append_character_revision(
            object(),  # type: ignore[arg-type]
            expected_version=ConcurrencyVersion(1),
            revision_id=revision_id(4),
            name=CharacterName("角色"),
            role=CharacterRole(),
            profile=CharacterProfile(),
            now=BASE_TIME,
        )


@pytest.mark.parametrize("expected", [True, 1.0])
def test_append_rejects_non_version_expected_values(expected: object) -> None:
    with pytest.raises(InvalidConcurrencyVersion):
        append_character_revision(
            initial_aggregate(),
            expected_version=expected,  # type: ignore[arg-type]
            revision_id=revision_id(4),
            name=CharacterName("角色"),
            role=CharacterRole(),
            profile=CharacterProfile(),
            now=BASE_TIME,
        )


def test_stale_conflict_has_priority_and_preserves_expected_actual() -> None:
    aggregate = initial_aggregate(name=CANARY, role=CANARY, profile=CANARY)

    with pytest.raises(ConcurrencyConflict) as caught:
        append_character_revision(
            aggregate,
            expected_version=ConcurrencyVersion(2),
            revision_id=aggregate.current_revision.id,
            name=CharacterName("新角色"),
            role=CharacterRole("新角色"),
            profile=CharacterProfile("新正文"),
            now=BASE_TIME - timedelta(seconds=1),
        )

    assert caught.value.expected_version == 2
    assert caught.value.actual_version == 1
    assert CANARY not in str(caught.value)
    assert CANARY not in repr(caught.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"revision_id": character_id()},
        {"name": CharacterRole("wrong")},
        {"role": CharacterName("wrong")},
        {"profile": CharacterRole("wrong")},
        {"now": BASE_TIME.replace(tzinfo=None)},
        {"now": BASE_TIME - timedelta(microseconds=1)},
    ],
)
def test_append_rejects_invalid_new_state(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "expected_version": ConcurrencyVersion(1),
        "revision_id": revision_id(4),
        "name": CharacterName("角色"),
        "role": CharacterRole(),
        "profile": CharacterProfile(),
        "now": BASE_TIME,
    }
    arguments.update(changes)

    with pytest.raises(InvalidCharacterState):
        append_character_revision(
            initial_aggregate(),
            **arguments,  # type: ignore[arg-type]
        )


def test_append_rejects_reusing_current_revision_id() -> None:
    aggregate = initial_aggregate()

    with pytest.raises(InvalidCharacterState):
        append_character_revision(
            aggregate,
            expected_version=ConcurrencyVersion(1),
            revision_id=aggregate.current_revision.id,
            name=CharacterName("角色"),
            role=CharacterRole(),
            profile=CharacterProfile(),
            now=BASE_TIME,
        )


def test_one_hundred_revision_sequence_is_deterministic() -> None:
    aggregate = initial_aggregate()
    all_aggregates = [aggregate]
    all_revision_ids = {aggregate.current_revision.id}

    for number in range(2, 101):
        previous = aggregate
        previous_snapshot = (previous.character, previous.head, previous.current_revision)
        next_revision_id = revision_id(number + 2)
        aggregate = append_character_revision(
            previous,
            expected_version=ConcurrencyVersion(number - 1),
            revision_id=next_revision_id,
            name=CharacterName(f"角色{number}"),
            role=CharacterRole(f"角色定位{number}"),
            profile=CharacterProfile(f"角色卡{number}"),
            now=BASE_TIME + timedelta(seconds=number - 1),
        )
        assert (previous.character, previous.head, previous.current_revision) == previous_snapshot
        assert aggregate.current_revision.revision_number == RevisionNumber(number)
        assert aggregate.character.concurrency_version == ConcurrencyVersion(number)
        assert aggregate.character.id == all_aggregates[0].character.id
        assert aggregate.character.project_id == all_aggregates[0].character.project_id
        assert aggregate.head.revision_id == next_revision_id
        assert aggregate.current_revision.created_at >= previous.current_revision.created_at
        assert str(aggregate.current_revision.name) == f"角色{number}"
        assert str(aggregate.current_revision.role) == f"角色定位{number}"
        assert str(aggregate.current_revision.profile) == f"角色卡{number}"
        assert next_revision_id not in all_revision_ids
        all_revision_ids.add(next_revision_id)
        all_aggregates.append(aggregate)

    assert [item.current_revision.revision_number.value for item in all_aggregates] == list(
        range(1, 101)
    )
    assert [item.character.concurrency_version.value for item in all_aggregates] == list(
        range(1, 101)
    )
    assert len(all_revision_ids) == 100
