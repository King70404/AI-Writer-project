"""Two-service Character application concurrency over real SQLite."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from tests.backend.character_repository_support import (
    BASE_TIME,
    character_id,
    character_revision_id,
    create_project,
    later,
    repository_database,
)

from aiwebnovel.character.application.commands import (
    CreateCharacterCommand,
    ReviseCharacterCommand,
)
from aiwebnovel.character.application.models import CharacterSnapshot
from aiwebnovel.character.application.services import CharacterCommandService
from aiwebnovel.character.persistence.repository import SqlAlchemyCharacterRepository
from aiwebnovel.domain.errors import ConcurrencyConflict

pytestmark = pytest.mark.integration


def test_two_services_produce_one_snapshot_and_one_conflict(tmp_path: Path) -> None:
    barrier = Barrier(2)
    clock_calls: list[list[int]] = [[], []]
    factory_calls: list[list[int]] = [[], []]

    with repository_database(tmp_path) as database:
        owner = create_project(database)
        initial = CharacterCommandService(
            database.repository,
            lambda: BASE_TIME,
            lambda: character_id(301),
            lambda: character_revision_id(401),
        ).create_character(
            CreateCharacterCommand(
                str(owner.project.id),
                "Initial",
                "Initial Role",
                "initial profile",
            )
        )
        sibling = CharacterCommandService(
            database.repository,
            lambda: BASE_TIME,
            lambda: character_id(302),
            lambda: character_revision_id(402),
        ).create_character(
            CreateCharacterCommand(
                str(owner.project.id),
                "Sibling",
                "Unaffected",
                "unchanged",
            )
        )
        repositories = (
            SqlAlchemyCharacterRepository(database.session_factory),
            SqlAlchemyCharacterRepository(database.session_factory),
        )

        def make_service(index: int) -> CharacterCommandService:
            def clock():
                clock_calls[index].append(index)
                return later()

            def revision_factory():
                factory_calls[index].append(index)
                return character_revision_id(403 + index)

            return CharacterCommandService(
                repositories[index],
                clock,
                lambda: character_id(900 + index),
                revision_factory,
            )

        services = (make_service(0), make_service(1))

        def revise(index: int) -> CharacterSnapshot:
            barrier.wait()
            return services[index].revise_character(
                ReviseCharacterCommand(
                    initial.character_id,
                    1,
                    f"Candidate {index}",
                    f"Role {index}",
                    f"profile {index}",
                )
            )

        outcomes: list[CharacterSnapshot | Exception] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(revise, index) for index in range(2)]
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=10))
                except Exception as exc:  # noqa: BLE001 - exact outcomes asserted below
                    outcomes.append(exc)

        with database.engine.connect() as connection:
            revisions = connection.exec_driver_sql(
                "SELECT id, revision_number, name, role, profile "
                "FROM character_revisions WHERE character_id = ? "
                "ORDER BY revision_number",
                (initial.character_id,),
            ).all()
            head_revision_id = connection.exec_driver_sql(
                "SELECT revision_id FROM character_heads WHERE character_id = ?",
                (initial.character_id,),
            ).scalar_one()
            sibling_state = connection.exec_driver_sql(
                "SELECT concurrency_version FROM characters WHERE id = ?",
                (sibling.character_id,),
            ).scalar_one()

    successes = [item for item in outcomes if type(item) is CharacterSnapshot]
    conflicts = [item for item in outcomes if type(item) is ConcurrencyConflict]
    assert len(successes) == 1
    assert len(conflicts) == 1
    success = successes[0]
    assert isinstance(success, CharacterSnapshot)
    assert success.concurrency_version == success.revision_number == 2
    winner = int(success.name.rsplit(" ", maxsplit=1)[1])
    loser = 1 - winner
    assert clock_calls[winner] == [winner]
    assert factory_calls[winner] == [winner]
    assert clock_calls[loser] == []
    assert factory_calls[loser] == []
    assert revisions == [
        (
            str(character_revision_id(401)),
            1,
            "Initial",
            "Initial Role",
            "initial profile",
        ),
        (
            str(character_revision_id(403 + winner)),
            2,
            f"Candidate {winner}",
            f"Role {winner}",
            f"profile {winner}",
        ),
    ]
    assert head_revision_id == str(character_revision_id(403 + winner))
    assert f"Candidate {loser}" not in {row[2] for row in revisions}
    assert f"profile {loser}" not in {row[4] for row in revisions}
    assert all(str(character_revision_id(403 + loser)) != row[0] for row in revisions)
    assert sibling_state == 1
