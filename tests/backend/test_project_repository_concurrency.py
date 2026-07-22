"""Deterministic SQLite concurrent Project append tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest
from tests.backend.project_repository_support import (
    aggregate,
    later,
    repository_database,
    revision_id,
    table_state,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("iteration", range(4))
def test_two_repository_instances_produce_one_success_and_one_stale_conflict(
    tmp_path: Path,
    iteration: int,
) -> None:
    initial = aggregate(iteration + 1)
    barrier = Barrier(2)
    called_ids: list[int] = []
    called_ids_lock = Lock()

    with repository_database(tmp_path) as database:
        database.repository.create(initial)
        repositories = (
            SqlAlchemyProjectRepository(database.session_factory),
            SqlAlchemyProjectRepository(database.session_factory),
        )

        def append(index: int) -> object:
            candidate = 40_000 + iteration * 10 + index

            def id_factory() -> object:
                with called_ids_lock:
                    called_ids.append(candidate)
                return revision_id(candidate)

            barrier.wait()
            return repositories[index].append_revision(
                initial.project.id,
                ConcurrencyVersion(1),
                ProjectTitle(f"Concurrent {index}"),
                ProjectDescription(f"Candidate {index}"),
                clock=lambda: later(),
                revision_id_factory=id_factory,  # type: ignore[arg-type]
            )

        outcomes: list[object] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(append, index) for index in range(2)]
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=10))
                except Exception as exc:  # noqa: BLE001 - assertions inspect exact outcome
                    outcomes.append(exc)

        successes = [item for item in outcomes if not isinstance(item, Exception)]
        conflicts = [item for item in outcomes if isinstance(item, ConcurrencyConflict)]
        restored = database.repository.get(initial.project.id)
        state = table_state(database.engine)
        with database.engine.connect() as connection:
            revisions = connection.exec_driver_sql(
                "SELECT id, revision_number FROM project_revisions "
                "WHERE project_id = ? ORDER BY revision_number",
                (str(initial.project.id),),
            ).all()

    assert len(successes) == 1
    assert len(conflicts) == 1
    assert len(outcomes) == 2
    assert len(called_ids) == 1
    assert restored is not None
    assert int(restored.project.concurrency_version) == 2
    assert int(restored.current_revision.revision_number) == 2
    assert state["projects"] == 1
    assert state["project_revisions"] == 2
    assert state["project_heads"] == 1
    assert revisions == [
        (str(initial.current_revision.id), 1),
        (str(revision_id(called_ids[0])), 2),
    ]
    assert state["head_revision_id"] == str(revision_id(called_ids[0]))
