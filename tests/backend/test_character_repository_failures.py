"""Character repository validation and rollback failure tests."""

from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from tests.backend.character_repository_support import (
    character_aggregate,
    character_revision_id,
    create_project,
    later,
    repository_database,
    table_state,
)

from aiwebnovel.character.errors import (
    CharacterAlreadyExists,
    CharacterDataCorruption,
    CharacterNotFound,
    CharacterProjectNotFound,
    CharacterRepositoryError,
    InvalidCharacterState,
)
from aiwebnovel.character.persistence.models import CharacterHeadRecord, CharacterRecord
from aiwebnovel.character.persistence.repository import SqlAlchemyCharacterRepository
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyConflict, ConcurrencyVersion

pytestmark = pytest.mark.integration


def test_constructor_and_invalid_inputs_fail_before_opening_session() -> None:
    with pytest.raises(TypeError):
        SqlAlchemyCharacterRepository(None)  # type: ignore[arg-type]

    sessions = 0

    def session_factory():
        nonlocal sessions
        sessions += 1
        raise AssertionError("session must not be opened")

    repository = SqlAlchemyCharacterRepository(session_factory)
    with pytest.raises(InvalidCharacterState):
        repository.create(object())  # type: ignore[arg-type]
    with pytest.raises(InvalidCharacterState):
        repository.get("bad-id")  # type: ignore[arg-type]
    with pytest.raises(InvalidCharacterState):
        repository.append_revision(
            character_aggregate().character.id,
            expected_version=ConcurrencyVersion(1),
            name=CharacterName("Valid"),
            role=CharacterRole(),
            profile=CharacterProfile(),
            clock=None,  # type: ignore[arg-type]
            revision_id_factory=lambda: character_revision_id(1),
        )

    assert sessions == 0


def test_session_factory_failure_is_safely_wrapped() -> None:
    def fail_session():
        raise RuntimeError("CHARACTER_PERSISTENCE_SECRET_CANARY")

    repository = SqlAlchemyCharacterRepository(fail_session)
    with pytest.raises(CharacterRepositoryError) as captured:
        repository.get(character_aggregate().character.id)

    assert str(captured.value) == ("The Character persistence operation could not be completed.")
    assert "CANARY" not in str(captured.value)


def test_specific_errors_reject_invalid_identifier_payloads() -> None:
    for error_type in (
        CharacterAlreadyExists,
        CharacterNotFound,
        CharacterProjectNotFound,
    ):
        with pytest.raises(InvalidCharacterState):
            error_type("invalid")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "failure",
    [
        SQLAlchemyError("CHARACTER_PERSISTENCE_SECRET_CANARY"),
        RuntimeError("CHARACTER_PERSISTENCE_SECRET_CANARY"),
    ],
)
def test_read_failures_roll_back_close_and_wrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    closed = 0
    rolled_back = 0
    with repository_database(tmp_path) as database:
        session = database.session_factory()
        original_close = session.close
        original_rollback = session.rollback

        def close() -> None:
            nonlocal closed
            closed += 1
            original_close()

        def rollback() -> None:
            nonlocal rolled_back
            rolled_back += 1
            original_rollback()

        def fail(*_args: object, **_kwargs: object) -> object:
            raise failure

        monkeypatch.setattr(session, "close", close)
        monkeypatch.setattr(session, "rollback", rollback)
        monkeypatch.setattr(session, "execute", fail)
        repository = SqlAlchemyCharacterRepository(lambda: session)
        with pytest.raises(CharacterRepositoryError) as captured:
            repository.get(character_aggregate().character.id)

    assert rolled_back == 1
    assert closed == 1
    assert "CANARY" not in str(captured.value)


@pytest.mark.parametrize(
    ("operation", "failure_point"),
    [
        ("create", "flush"),
        ("create", "commit"),
        ("append", "flush"),
        ("append", "commit"),
    ],
)
def test_late_session_failure_rolls_back_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    failure_point: str,
) -> None:
    initial = character_aggregate()
    closed = 0
    with repository_database(tmp_path) as database:
        create_project(database)
        if operation == "append":
            database.repository.create(initial)
        before = table_state(database.engine)
        session = database.session_factory()
        original_close = session.close

        def close() -> None:
            nonlocal closed
            closed += 1
            original_close()

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("CHARACTER_PERSISTENCE_SECRET_CANARY")

        monkeypatch.setattr(session, "close", close)
        monkeypatch.setattr(session, failure_point, fail)
        repository = SqlAlchemyCharacterRepository(lambda: session)
        with pytest.raises(CharacterRepositoryError) as captured:
            if operation == "create":
                repository.create(initial)
            else:
                repository.append_revision(
                    initial.character.id,
                    expected_version=ConcurrencyVersion(1),
                    name=CharacterName("late failure"),
                    role=CharacterRole(),
                    profile=CharacterProfile(),
                    clock=lambda: later(),
                    revision_id_factory=lambda: character_revision_id(30_002),
                )
        after = table_state(database.engine)

    assert closed == 1
    assert after == before
    assert "CANARY" not in str(captured.value)


@pytest.mark.parametrize("cas_target", ["stable", "head"])
def test_cas_miss_rolls_back_insert_and_pointer_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cas_target: str,
) -> None:
    initial = character_aggregate()
    if cas_target == "stable":

        def miss(*_args: object):
            return (
                update(CharacterRecord)
                .values(concurrency_version=CharacterRecord.concurrency_version)
                .where(CharacterRecord.id.is_(None))
            )

        monkeypatch.setattr(
            "aiwebnovel.character.persistence.repository.character_compare_and_swap",
            miss,
        )
        expected_error: type[Exception] = ConcurrencyConflict
    else:

        def miss(*_args: object):
            return (
                update(CharacterHeadRecord)
                .values(revision_id=CharacterHeadRecord.revision_id)
                .where(CharacterHeadRecord.character_id.is_(None))
            )

        monkeypatch.setattr(
            "aiwebnovel.character.persistence.repository.character_head_compare_and_swap",
            miss,
        )
        expected_error = CharacterDataCorruption

    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(expected_error):
            database.repository.append_revision(
                initial.character.id,
                expected_version=ConcurrencyVersion(1),
                name=CharacterName("Must roll back"),
                role=CharacterRole(),
                profile=CharacterProfile(),
                clock=lambda: later(),
                revision_id_factory=lambda: character_revision_id(30_002),
            )
        after = table_state(database.engine)

    assert after == before


def test_runtime_protocol_surface_is_exact() -> None:
    assert all(
        callable(getattr(SqlAlchemyCharacterRepository, name))
        for name in ("create", "get", "append_revision")
    )
    assert not hasattr(SqlAlchemyCharacterRepository, "get_for_project")
