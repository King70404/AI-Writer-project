"""Transactional Character revision append tests."""

from pathlib import Path

import pytest
from sqlalchemy import event
from tests.backend.character_repository_support import (
    character_aggregate,
    character_id,
    character_revision_id,
    create_project,
    later,
    repository_database,
    table_state,
)

from aiwebnovel.character.errors import (
    CharacterNotFound,
    CharacterRepositoryError,
    InvalidCharacterState,
)
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyConflict, ConcurrencyVersion

pytestmark = pytest.mark.integration


def test_append_is_complete_replacement_and_preserves_prior_revision(
    tmp_path: Path,
) -> None:
    initial = character_aggregate(name="First", role="Hero", profile="Old")
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        returned = database.repository.append_revision(
            initial.character.id,
            expected_version=ConcurrencyVersion(1),
            name=CharacterName("Second"),
            role=CharacterRole(""),
            profile=CharacterProfile(""),
            clock=lambda: later(),
            revision_id_factory=lambda: character_revision_id(30_002),
        )
        loaded = database.repository.get(initial.character.id)
        with database.engine.connect() as connection:
            revisions = connection.exec_driver_sql(
                "SELECT revision_number, name, role, profile "
                "FROM character_revisions WHERE character_id = ? "
                "ORDER BY revision_number",
                (str(initial.character.id),),
            ).all()

    assert returned == loaded
    assert returned.character.concurrency_version == ConcurrencyVersion(2)
    assert returned.current_revision.revision_number.value == 2
    assert str(returned.current_revision.name) == "Second"
    assert str(returned.current_revision.role) == ""
    assert str(returned.current_revision.profile) == ""
    assert revisions == [(1, "First", "Hero", "Old"), (2, "Second", "", "")]


def test_stale_append_has_no_clock_factory_or_write_side_effect(
    tmp_path: Path,
) -> None:
    initial = character_aggregate()
    calls: list[str] = []
    statements: list[str] = []
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(database.engine, "before_cursor_execute", capture)
        try:
            with pytest.raises(ConcurrencyConflict) as captured:
                database.repository.append_revision(
                    initial.character.id,
                    expected_version=ConcurrencyVersion(2),
                    name=CharacterName("Stale"),
                    role=CharacterRole(),
                    profile=CharacterProfile(),
                    clock=lambda: calls.append("clock") or later(),
                    revision_id_factory=lambda: (
                        calls.append("factory") or character_revision_id(30_002)
                    ),
                )
        finally:
            event.remove(database.engine, "before_cursor_execute", capture)
        after = table_state(database.engine)

    assert captured.value.expected_version == 2
    assert captured.value.actual_version == 1
    assert calls == []
    assert after == before
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for statement in statements
    )


def test_missing_character_precedes_clock_and_factory(tmp_path: Path) -> None:
    calls: list[str] = []
    with (
        repository_database(tmp_path) as database,
        pytest.raises(CharacterNotFound),
    ):
        database.repository.append_revision(
            character_id(404),
            expected_version=ConcurrencyVersion(1),
            name=CharacterName("Missing"),
            role=CharacterRole(),
            profile=CharacterProfile(),
            clock=lambda: calls.append("clock") or later(),
            revision_id_factory=lambda: calls.append("factory") or character_revision_id(30_002),
        )

    assert calls == []


@pytest.mark.parametrize("failure_source", ["clock", "factory"])
def test_clock_or_factory_failure_rolls_back_without_partial_revision(
    tmp_path: Path,
    failure_source: str,
) -> None:
    initial = character_aggregate()
    calls: list[str] = []

    def fail() -> None:
        raise RuntimeError("CHARACTER_PERSISTENCE_SECRET_CANARY")

    def clock() -> object:
        calls.append("clock")
        if failure_source == "clock":
            return fail()
        return later()

    def factory() -> object:
        calls.append("factory")
        if failure_source == "factory":
            return fail()
        return character_revision_id(30_002)

    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(Exception) as captured:
            database.repository.append_revision(
                initial.character.id,
                expected_version=ConcurrencyVersion(1),
                name=CharacterName("Second"),
                role=CharacterRole(),
                profile=CharacterProfile(),
                clock=clock,  # type: ignore[arg-type]
                revision_id_factory=factory,  # type: ignore[arg-type]
            )
        after = table_state(database.engine)

    assert calls == (["clock"] if failure_source == "clock" else ["clock", "factory"])
    assert after == before
    assert "CANARY" not in str(captured.value)


def test_clock_rollback_and_duplicate_revision_id_leave_state_unchanged(
    tmp_path: Path,
) -> None:
    initial = character_aggregate()
    sibling = character_aggregate(2, project_value=1)
    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        database.repository.create(sibling)
        before = table_state(database.engine)
        with pytest.raises(InvalidCharacterState):
            database.repository.append_revision(
                initial.character.id,
                expected_version=ConcurrencyVersion(1),
                name=CharacterName("Clock rollback"),
                role=CharacterRole(),
                profile=CharacterProfile(),
                clock=lambda: later(-1),
                revision_id_factory=lambda: character_revision_id(30_002),
            )
        with pytest.raises(CharacterRepositoryError):
            database.repository.append_revision(
                initial.character.id,
                expected_version=ConcurrencyVersion(1),
                name=CharacterName("Duplicate revision"),
                role=CharacterRole(),
                profile=CharacterProfile(),
                clock=lambda: later(),
                revision_id_factory=lambda: sibling.current_revision.id,
            )
        after = table_state(database.engine)

    assert after == before


def test_factory_wrong_type_is_rejected_without_repr_or_writes(tmp_path: Path) -> None:
    initial = character_aggregate()

    class Hostile:
        def __repr__(self) -> str:
            raise AssertionError("repr must not be called")

    with repository_database(tmp_path) as database:
        create_project(database)
        database.repository.create(initial)
        before = table_state(database.engine)
        with pytest.raises(InvalidCharacterState) as captured:
            database.repository.append_revision(
                initial.character.id,
                expected_version=ConcurrencyVersion(1),
                name=CharacterName("Wrong factory"),
                role=CharacterRole(),
                profile=CharacterProfile(),
                clock=lambda: later(),
                revision_id_factory=lambda: Hostile(),  # type: ignore[return-value]
            )
        after = table_state(database.engine)

    assert after == before
    assert "Hostile" not in str(captured.value)


def test_updating_one_character_does_not_change_its_sibling_or_other_modules(
    tmp_path: Path,
) -> None:
    first = character_aggregate(1, name="Same", role="Same", profile="Same")
    second = character_aggregate(
        2,
        project_value=1,
        name="Same",
        role="Same",
        profile="Same",
    )
    with repository_database(tmp_path) as database:
        project = create_project(database)
        database.repository.create(first)
        database.repository.create(second)
        with database.engine.connect() as connection:
            project_before = connection.exec_driver_sql(
                "SELECT concurrency_version, updated_at FROM projects WHERE id = ?",
                (str(project.project.id),),
            ).one()
            story_before = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM story_bibles"
            ).scalar_one()
        updated = database.repository.append_revision(
            first.character.id,
            expected_version=ConcurrencyVersion(1),
            name=CharacterName("Changed"),
            role=CharacterRole("Changed"),
            profile=CharacterProfile("Changed"),
            clock=lambda: later(),
            revision_id_factory=lambda: character_revision_id(30_002),
        )
        sibling = database.repository.get(second.character.id)
        with database.engine.connect() as connection:
            project_after = connection.exec_driver_sql(
                "SELECT concurrency_version, updated_at FROM projects WHERE id = ?",
                (str(project.project.id),),
            ).one()
            story_after = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM story_bibles"
            ).scalar_one()
            heads = connection.exec_driver_sql(
                "SELECT character_id, revision_id FROM character_heads ORDER BY character_id"
            ).all()

    assert str(updated.current_revision.name) == "Changed"
    assert sibling == second
    assert project_after == project_before
    assert story_after == story_before == 0
    assert heads == [
        (str(first.character.id), str(updated.current_revision.id)),
        (str(second.character.id), str(second.current_revision.id)),
    ]
