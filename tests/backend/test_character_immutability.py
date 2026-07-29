"""Strong immutability and import-side-effect checks for Character."""

import importlib
import os
import sqlite3
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from fastapi import FastAPI
from tests.backend.character_support import BASE_TIME, initial_aggregate, revision_id

import aiwebnovel as aiwebnovel_package
import aiwebnovel.project as project_package
import aiwebnovel.story_bible as story_bible_package
from aiwebnovel.character import (
    CharacterId,
    CharacterName,
    CharacterProfile,
    CharacterRevisionId,
    CharacterRole,
    append_character_revision,
)
from aiwebnovel.db.base import Base
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.identifiers import Ulid


@pytest.mark.parametrize(
    ("value", "attribute", "replacement"),
    [
        (CharacterName("角色"), "value", "修改"),
        (CharacterRole("主角"), "value", "修改"),
        (CharacterProfile("正文"), "value", "修改"),
        (CharacterId.from_ulid(Ulid.from_parts(1, 1)), "prefix", "bad"),
        (CharacterRevisionId.from_ulid(Ulid.from_parts(1, 2)), "ulid", Ulid.from_int(3)),
        (initial_aggregate().character, "project_id", object()),
        (initial_aggregate().current_revision, "profile", CharacterProfile("修改")),
        (initial_aggregate().head, "revision_id", revision_id(20)),
        (initial_aggregate(), "current_revision", object()),
    ],
)
def test_domain_objects_reject_field_mutation(
    value: object,
    attribute: str,
    replacement: object,
) -> None:
    with pytest.raises((FrozenInstanceError, AttributeError)):
        setattr(value, attribute, replacement)


def test_slots_values_expose_no_mutable_instance_dictionary_or_containers() -> None:
    aggregate = initial_aggregate()
    values = (
        CharacterName("角色"),
        CharacterRole("主角"),
        CharacterProfile("正文"),
        aggregate.character.id,
        aggregate.current_revision.id,
        aggregate.character,
        aggregate.current_revision,
        aggregate.head,
        aggregate,
    )

    assert all(not hasattr(value, "__dict__") for value in values)
    assert all(
        not isinstance(field_value, (list, dict, set))
        for value in values
        for field_name in getattr(value, "__slots__", ())
        for field_value in [getattr(value, field_name)]
    )


def test_append_returns_new_entities_without_mutating_old_state() -> None:
    old = initial_aggregate()
    old_snapshot = (old.character, old.head, old.current_revision)

    new = append_character_revision(
        old,
        expected_version=ConcurrencyVersion(1),
        revision_id=revision_id(4),
        name=CharacterName("新角色"),
        role=CharacterRole("新定位"),
        profile=CharacterProfile("新正文"),
        now=BASE_TIME,
    )

    assert (old.character, old.head, old.current_revision) == old_snapshot
    assert new.character is not old.character
    assert new.head is not old.head
    assert new.current_revision is not old.current_revision


def test_character_domain_exposes_no_in_place_history_or_relationship_api() -> None:
    import aiwebnovel.character as character

    exported_names = set(dir(character))

    assert "update_in_place" not in exported_names
    assert "delete_revision" not in exported_names
    assert "restore_revision" not in exported_names
    assert "edit_relationship" not in exported_names
    assert "Repository" not in exported_names
    assert "Session" not in exported_names


def test_import_has_no_database_route_clock_id_or_module_state_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_before = tuple(sorted(Base.metadata.tables))
    project_state_before = dict(vars(project_package))
    story_bible_state_before = dict(vars(story_bible_package))
    calls = {"connect": 0, "getenv": 0, "mkdir": 0, "route": 0, "ulid": 0}

    def forbidden(name: str):
        def record(*_args: object, **_kwargs: object) -> object:
            calls[name] += 1
            raise AssertionError(f"unexpected {name} side effect")

        return record

    monkeypatch.setattr(sqlite3, "connect", forbidden("connect"))
    monkeypatch.setattr(os, "getenv", forbidden("getenv"))
    monkeypatch.setattr(Path, "mkdir", forbidden("mkdir"))
    monkeypatch.setattr(FastAPI, "add_api_route", forbidden("route"))
    identifier_module = importlib.import_module("aiwebnovel.domain.identifiers")
    monkeypatch.setattr(identifier_module, "new_ulid", forbidden("ulid"))
    for module_name in tuple(sys.modules):
        if module_name == "aiwebnovel.character" or module_name.startswith("aiwebnovel.character."):
            monkeypatch.delitem(sys.modules, module_name)
    if hasattr(aiwebnovel_package, "character"):
        monkeypatch.delattr(aiwebnovel_package, "character")

    imported = importlib.import_module("aiwebnovel.character")

    assert imported.CharacterId.__name__ == "CharacterId"
    assert tuple(sorted(Base.metadata.tables)) == metadata_before
    assert dict(vars(project_package)) == project_state_before
    assert dict(vars(story_bible_package)) == story_bible_state_before
    assert calls == {"connect": 0, "getenv": 0, "mkdir": 0, "route": 0, "ulid": 0}
