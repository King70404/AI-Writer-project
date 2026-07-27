"""Strong immutability and import-side-effect checks for Story Bible."""

import importlib
import os
import sqlite3
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from fastapi import FastAPI
from tests.backend.story_bible_support import (
    BASE_TIME,
    initial_aggregate,
    revision_id,
)

import aiwebnovel as aiwebnovel_package
import aiwebnovel.project as project_package
from aiwebnovel.db.base import Base
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.identifiers import Ulid
from aiwebnovel.story_bible import (
    StoryBibleContent,
    StoryBibleId,
    StoryBibleRevisionId,
    StoryBibleTitle,
    append_story_bible_revision,
)


@pytest.mark.parametrize(
    ("value", "attribute", "replacement"),
    [
        (StoryBibleTitle("设定"), "value", "修改"),
        (StoryBibleContent("正文"), "value", "修改"),
        (StoryBibleId.from_ulid(Ulid.from_parts(1, 1)), "prefix", "bad"),
        (StoryBibleRevisionId.from_ulid(Ulid.from_parts(1, 2)), "ulid", Ulid.from_int(3)),
        (initial_aggregate().story_bible, "project_id", object()),
        (initial_aggregate().current_revision, "title", StoryBibleTitle("修改")),
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


def test_slots_values_expose_no_mutable_instance_dictionary() -> None:
    aggregate = initial_aggregate()
    values = (
        StoryBibleTitle("设定"),
        StoryBibleContent("正文"),
        aggregate.story_bible.id,
        aggregate.current_revision.id,
        aggregate.story_bible,
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


def test_append_returns_new_objects_without_mutating_or_sharing_entities() -> None:
    old = initial_aggregate()
    old_snapshot = (old.story_bible, old.head, old.current_revision)

    new = append_story_bible_revision(
        old,
        expected_version=ConcurrencyVersion(1),
        revision_id=revision_id(4),
        title=StoryBibleTitle("新设定"),
        content=StoryBibleContent("新正文"),
        now=BASE_TIME,
    )

    assert (old.story_bible, old.head, old.current_revision) == old_snapshot
    assert new.story_bible is not old.story_bible
    assert new.head is not old.head
    assert new.current_revision is not old.current_revision


def test_story_bible_domain_exposes_no_in_place_or_revision_deletion_api() -> None:
    import aiwebnovel.story_bible as story_bible

    exported_names = set(dir(story_bible))

    assert "update_in_place" not in exported_names
    assert "delete_revision" not in exported_names
    assert "Repository" not in exported_names
    assert "Session" not in exported_names


def test_import_has_no_database_files_routes_clock_ids_or_project_state_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_before = tuple(sorted(Base.metadata.tables))
    project_state_before = dict(vars(project_package))
    calls = {
        "connect": 0,
        "getenv": 0,
        "mkdir": 0,
        "route": 0,
        "ulid": 0,
    }

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
    monkeypatch.setattr(
        aiwebnovel_package,
        "story_bible",
        aiwebnovel_package.story_bible,
    )
    for module_name in tuple(sys.modules):
        if module_name == "aiwebnovel.story_bible" or module_name.startswith(
            "aiwebnovel.story_bible."
        ):
            monkeypatch.delitem(sys.modules, module_name)

    imported = importlib.import_module("aiwebnovel.story_bible")

    assert imported.StoryBibleId.__name__ == "StoryBibleId"
    assert tuple(sorted(Base.metadata.tables)) == metadata_before
    assert dict(vars(project_package)) == project_state_before
    assert calls == {
        "connect": 0,
        "getenv": 0,
        "mkdir": 0,
        "route": 0,
        "ulid": 0,
    }
