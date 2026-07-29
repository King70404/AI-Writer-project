"""Character aggregate-to-snapshot mapping."""

from dataclasses import replace

import pytest
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_aggregate,
)

from aiwebnovel.character.application.mappers import (
    character_snapshot_from_aggregate,
)
from aiwebnovel.character.errors import InvalidCharacterState

CANARY = "CHARACTER_APPLICATION_SECRET_CANARY"


def test_mapper_explicitly_maps_every_field_without_mutating_aggregate() -> None:
    aggregate = character_aggregate(
        name="Name",
        role="Role",
        profile="Profile",
    )

    snapshot = character_snapshot_from_aggregate(aggregate)

    assert snapshot.character_id == str(aggregate.character.id)
    assert snapshot.project_id == str(aggregate.character.project_id)
    assert snapshot.current_revision_id == str(aggregate.current_revision.id)
    assert snapshot.revision_number == 1
    assert snapshot.concurrency_version == 1
    assert (snapshot.name, snapshot.role, snapshot.profile) == (
        "Name",
        "Role",
        "Profile",
    )
    assert (
        snapshot.created_at,
        snapshot.updated_at,
        snapshot.revision_created_at,
        snapshot.head_updated_at,
    ) == (BASE_TIME, BASE_TIME, BASE_TIME, BASE_TIME)
    assert aggregate == character_aggregate(name="Name", role="Role", profile="Profile")


@pytest.mark.parametrize("value", [None, object(), "aggregate", 1, True])
def test_mapper_rejects_non_aggregate_without_repr_or_card_leak(value: object) -> None:
    with pytest.raises(InvalidCharacterState) as captured:
        character_snapshot_from_aggregate(value)  # type: ignore[arg-type]
    assert CANARY not in str(captured.value)


def test_mapper_revalidates_snapshot_invariants() -> None:
    aggregate = character_aggregate(profile=CANARY)
    broken = replace(
        aggregate,
        character=replace(
            aggregate.character,
            updated_at=aggregate.character.updated_at,
        ),
    )

    snapshot = character_snapshot_from_aggregate(broken)

    assert snapshot.profile == CANARY
