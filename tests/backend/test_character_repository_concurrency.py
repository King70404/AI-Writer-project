"""Deterministic SQLite concurrent Character append tests."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest
from tests.backend.character_repository_support import (
    character_aggregate,
    character_revision_id,
    create_project,
    later,
    repository_database,
    table_state,
)

from aiwebnovel.character.persistence.repository import SqlAlchemyCharacterRepository
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("iteration", range(4))
def test_two_repositories_produce_one_success_and_one_stale_conflict(
    tmp_path: Path,
    iteration: int,
) -> None:
    initial = character_aggregate(iteration + 1)
    barrier = Barrier(2)
    called_ids: list[int] = []
    called_clocks: list[int] = []
    calls_lock = Lock()

    with repository_database(tmp_path) as database:
        create_project(database, iteration + 1)
        database.repository.create(initial)
        repositories = (
            SqlAlchemyCharacterRepository(database.session_factory),
            SqlAlchemyCharacterRepository(database.session_factory),
        )

        def append(index: int) -> object:
            candidate = 40_000 + iteration * 10 + index

            def id_factory():
                with calls_lock:
                    called_ids.append(candidate)
                return character_revision_id(candidate)

            def clock():
                with calls_lock:
                    called_clocks.append(index)
                return later()

            barrier.wait()
            return repositories[index].append_revision(
                initial.character.id,
                expected_version=ConcurrencyVersion(1),
                name=CharacterName(f"Concurrent {index}"),
                role=CharacterRole(f"Candidate {index}"),
                profile=CharacterProfile(f"Profile {index}"),
                clock=clock,
                revision_id_factory=id_factory,
            )

        outcomes: list[object] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(append, index) for index in range(2)]
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=10))
                except Exception as exc:  # noqa: BLE001 - exact outcomes asserted below
                    outcomes.append(exc)

        successes = [item for item in outcomes if not isinstance(item, Exception)]
        conflicts = [item for item in outcomes if isinstance(item, ConcurrencyConflict)]
        restored = database.repository.get(initial.character.id)
        state = table_state(database.engine, iteration + 1)
        with database.engine.connect() as connection:
            revisions = connection.exec_driver_sql(
                "SELECT id, revision_number, name, role, profile "
                "FROM character_revisions "
                "WHERE character_id = ? ORDER BY revision_number",
                (str(initial.character.id),),
            ).all()

    assert len(successes) == 1
    assert len(conflicts) == 1
    assert len(called_ids) == 1
    assert len(called_clocks) == 1
    assert restored is not None
    assert int(restored.character.concurrency_version) == 2
    assert state["characters"] == 1
    assert state["character_revisions"] == 2
    assert state["character_heads"] == 1
    assert revisions[0] == (
        str(initial.current_revision.id),
        1,
        str(initial.current_revision.name),
        str(initial.current_revision.role),
        str(initial.current_revision.profile),
    )
    assert revisions[1][0:2] == (str(character_revision_id(called_ids[0])), 2)
    assert revisions[1][2:] in {
        ("Concurrent 0", "Candidate 0", "Profile 0"),
        ("Concurrent 1", "Candidate 1", "Profile 1"),
    }
    assert state["head_revision_id"] == str(character_revision_id(called_ids[0]))
