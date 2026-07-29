"""Explicit pure mapping from Character aggregate to detached snapshot."""

from aiwebnovel.character.application.models import CharacterSnapshot
from aiwebnovel.character.entities import CharacterAggregate
from aiwebnovel.character.errors import InvalidCharacterState


def character_snapshot_from_aggregate(
    aggregate: CharacterAggregate,
) -> CharacterSnapshot:
    """Map every current Character field without reflection or side effects."""
    if type(aggregate) is not CharacterAggregate:
        raise InvalidCharacterState
    return CharacterSnapshot(
        character_id=str(aggregate.character.id),
        project_id=str(aggregate.character.project_id),
        current_revision_id=str(aggregate.current_revision.id),
        revision_number=int(aggregate.current_revision.revision_number),
        concurrency_version=int(aggregate.character.concurrency_version),
        name=str(aggregate.current_revision.name),
        role=str(aggregate.current_revision.role),
        profile=str(aggregate.current_revision.profile),
        created_at=aggregate.character.created_at,
        updated_at=aggregate.character.updated_at,
        revision_created_at=aggregate.current_revision.created_at,
        head_updated_at=aggregate.head.updated_at,
    )


__all__ = ["character_snapshot_from_aggregate"]
