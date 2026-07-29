"""Explicit Character record mapper tests."""

from datetime import UTC

import pytest
from sqlalchemy import inspect
from tests.backend.character_repository_support import character_aggregate

from aiwebnovel.character.entities import Character, CharacterHead, CharacterRevision
from aiwebnovel.character.errors import CharacterDataCorruption, InvalidCharacterState
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.persistence.mappers import (
    character_aggregate_from_records,
    character_aggregate_to_records,
    character_from_record,
    character_head_from_record,
    character_head_to_record,
    character_revision_from_record,
    character_revision_to_record,
    character_to_record,
)
from aiwebnovel.character.persistence.models import (
    CharacterHeadRecord,
    CharacterRecord,
    CharacterRevisionRecord,
)
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId


def test_aggregate_maps_to_three_transient_records_and_back() -> None:
    aggregate = character_aggregate(
        name="  Lin Qiu  ",
        role="  Protagonist  ",
        profile="first\r\ncomplete card",
    )

    stable, head, revision = character_aggregate_to_records(aggregate)
    restored = character_aggregate_from_records(stable, head, revision)

    assert type(stable) is CharacterRecord
    assert type(head) is CharacterHeadRecord
    assert type(revision) is CharacterRevisionRecord
    assert type(stable.id) is CharacterId
    assert type(stable.project_id) is ProjectId
    assert type(stable.concurrency_version) is ConcurrencyVersion
    assert type(revision.id) is CharacterRevisionId
    assert type(revision.revision_number) is RevisionNumber
    assert restored == aggregate
    assert type(restored.character) is Character
    assert type(restored.head) is CharacterHead
    assert type(restored.current_revision) is CharacterRevision
    assert type(restored.current_revision.name) is CharacterName
    assert type(restored.current_revision.role) is CharacterRole
    assert type(restored.current_revision.profile) is CharacterProfile
    assert restored.character.created_at.tzinfo is UTC
    assert restored.head.updated_at.tzinfo is UTC
    assert inspect(stable).session is None
    assert inspect(head).session is None
    assert inspect(revision).session is None


def test_individual_record_mappers_restore_domain_values() -> None:
    aggregate = character_aggregate()
    stable, head, revision = character_aggregate_to_records(aggregate)

    assert character_from_record(stable) == aggregate.character
    assert character_head_from_record(head) == aggregate.head
    assert character_revision_from_record(revision) == aggregate.current_revision


def test_aggregate_mapper_rejects_cross_owned_head_and_revision() -> None:
    aggregate = character_aggregate()
    stable, head, revision = character_aggregate_to_records(aggregate)
    head.character_id = CharacterId.new()
    with pytest.raises(CharacterDataCorruption):
        character_aggregate_from_records(stable, head, revision)

    stable, head, revision = character_aggregate_to_records(aggregate)
    revision.character_id = CharacterId.new()
    with pytest.raises(CharacterDataCorruption):
        character_aggregate_from_records(stable, head, revision)


def test_record_to_domain_mappers_reject_wrong_or_invalid_records() -> None:
    with pytest.raises(CharacterDataCorruption):
        character_from_record(CharacterRevisionRecord())  # type: ignore[arg-type]
    with pytest.raises(CharacterDataCorruption):
        character_head_from_record(CharacterRecord())  # type: ignore[arg-type]
    with pytest.raises(CharacterDataCorruption):
        character_revision_from_record(CharacterHeadRecord())  # type: ignore[arg-type]

    aggregate = character_aggregate()
    stable, head, revision = character_aggregate_to_records(aggregate)
    stable.concurrency_version = 0  # type: ignore[assignment]
    head.updated_at = "not-a-time"  # type: ignore[assignment]
    revision.name = ""
    for mapper, record in (
        (character_from_record, stable),
        (character_head_from_record, head),
        (character_revision_from_record, revision),
    ):
        with pytest.raises(CharacterDataCorruption):
            mapper(record)  # type: ignore[arg-type]

    stable, _, _ = character_aggregate_to_records(aggregate)
    stable.id = "invalid-character-id"  # type: ignore[assignment]
    with pytest.raises(CharacterDataCorruption):
        character_from_record(stable)


def test_domain_to_record_mappers_reject_crossed_objects() -> None:
    aggregate = character_aggregate()
    with pytest.raises(InvalidCharacterState):
        character_to_record(aggregate.head)  # type: ignore[arg-type]
    with pytest.raises(InvalidCharacterState):
        character_head_to_record(aggregate.current_revision)  # type: ignore[arg-type]
    with pytest.raises(InvalidCharacterState):
        character_revision_to_record(aggregate.character)  # type: ignore[arg-type]
    with pytest.raises(InvalidCharacterState):
        character_aggregate_to_records(aggregate.character)  # type: ignore[arg-type]
