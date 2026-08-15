"""Deterministic concurrent append coverage for current position projections."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest
from tests.backend.novel_structure_repository_support import (
    create_project,
    later,
    repository_database,
    volume_aggregate,
    volume_revision_id,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.novel_structure import (
    NovelStructurePosition,
    NovelStructureSummary,
    NovelStructureTitle,
)
from aiwebnovel.novel_structure.persistence.repository import (
    SqlAlchemyNovelStructureRepository,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("iteration", range(2))
def test_two_volume_repositories_commit_one_revision_and_one_stale_conflict(
    tmp_path: Path,
    iteration: int,
) -> None:
    initial = volume_aggregate(iteration + 1, project_value=iteration + 1, position=1)
    barrier = Barrier(2)
    calls_lock = Lock()
    called_candidates: list[int] = []

    with repository_database(tmp_path) as database:
        create_project(database, iteration + 1)
        database.repository.create_volume(initial)
        repositories = (
            SqlAlchemyNovelStructureRepository(database.session_factory),
            SqlAlchemyNovelStructureRepository(database.session_factory),
        )

        def append(index: int) -> object:
            candidate = 50_000 + iteration * 10 + index

            def revision_factory():
                with calls_lock:
                    called_candidates.append(candidate)
                return volume_revision_id(candidate)

            barrier.wait()
            return repositories[index].append_volume_revision(
                initial.volume.id,
                expected_version=ConcurrencyVersion(1),
                title=NovelStructureTitle(f"Concurrent {index}"),
                summary=NovelStructureSummary(f"Candidate {index}"),
                position=NovelStructurePosition(index + 2),
                clock=lambda: later(),
                revision_id_factory=revision_factory,
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
        restored = database.repository.get_volume(initial.volume.id)
        with database.engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id, revision_number, title, summary, position "
                "FROM volume_revisions WHERE volume_id = ? ORDER BY revision_number",
                (str(initial.volume.id),),
            ).all()
            stable = connection.exec_driver_sql(
                "SELECT concurrency_version, current_position FROM volumes WHERE id = ?",
                (str(initial.volume.id),),
            ).one()
            head = connection.exec_driver_sql(
                "SELECT revision_id FROM volume_heads WHERE volume_id = ?",
                (str(initial.volume.id),),
            ).scalar_one()

    assert len(successes) == 1
    assert len(conflicts) == 1
    assert len(called_candidates) == 1
    assert restored is not None
    assert restored.volume.concurrency_version == ConcurrencyVersion(2)
    assert len(rows) == 2
    assert rows[0][0:2] == (str(initial.current_revision.id), 1)
    assert rows[1][0:2] == (str(volume_revision_id(called_candidates[0])), 2)
    assert rows[1][2:] in {
        ("Concurrent 0", "Candidate 0", 2),
        ("Concurrent 1", "Candidate 1", 3),
    }
    assert stable == (2, rows[1][4])
    assert head == rows[1][0]
