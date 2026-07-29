"""Deterministic Character domain fixtures."""

from datetime import UTC, datetime

from aiwebnovel.character import (
    CharacterAggregate,
    CharacterId,
    CharacterName,
    CharacterProfile,
    CharacterRevisionId,
    CharacterRole,
    create_initial_character,
)
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.project.identifiers import ProjectId

BASE_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def character_id(randomness: int = 1) -> CharacterId:
    return CharacterId.from_ulid(Ulid.from_parts(1, randomness))


def revision_id(randomness: int = 2) -> CharacterRevisionId:
    return CharacterRevisionId.from_ulid(Ulid.from_parts(1, randomness))


def project_id(randomness: int = 3) -> ProjectId:
    return ProjectId.from_ulid(Ulid.from_parts(1, randomness))


def initial_aggregate(
    *,
    name: str = "角色",
    role: str = "主角",
    profile: str = "角色卡正文",
) -> CharacterAggregate:
    return create_initial_character(
        character_id=character_id(),
        revision_id=revision_id(),
        project_id=project_id(),
        name=CharacterName(name),
        role=CharacterRole(role),
        profile=CharacterProfile(profile),
        now=BASE_TIME,
    )
