"""Deterministic SQLite concurrent Story Bible append tests."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock

import pytest
from tests.backend.story_bible_repository_support import (
    create_project,
    later,
    repository_database,
    story_bible_aggregate,
    story_bible_revision_id,
    table_state,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.story_bible.persistence.repository import (
    SqlAlchemyStoryBibleRepository,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("iteration", range(4))
def test_two_repository_instances_produce_one_success_and_one_stale_conflict(
    tmp_path: Path,
    iteration: int,
) -> None:
    initial = story_bible_aggregate(iteration + 1)
    barrier = Barrier(2)
    called_ids: list[int] = []
    called_clocks: list[int] = []
    called_ids_lock = Lock()

    with repository_database(tmp_path) as database:
        create_project(database, iteration + 1)
        database.repository.create(initial)
        repositories = (
            SqlAlchemyStoryBibleRepository(database.session_factory),
            SqlAlchemyStoryBibleRepository(database.session_factory),
        )

        def append(index: int) -> object:
            candidate = 40_000 + iteration * 10 + index

            def id_factory():
                with called_ids_lock:
                    called_ids.append(candidate)
                return story_bible_revision_id(candidate)

            def clock():
                with called_ids_lock:
                    called_clocks.append(index)
                return later()

            barrier.wait()
            return repositories[index].append_revision(
                initial.story_bible.id,
                expected_version=ConcurrencyVersion(1),
                title=StoryBibleTitle(f"Concurrent {index}"),
                content=StoryBibleContent(f"Candidate {index}"),
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
        restored = database.repository.get(initial.story_bible.id)
        state = table_state(database.engine)
        with database.engine.connect() as connection:
            revisions = connection.exec_driver_sql(
                "SELECT id, revision_number FROM story_bible_revisions "
                "WHERE story_bible_id = ? ORDER BY revision_number",
                (str(initial.story_bible.id),),
            ).all()

    assert len(successes) == 1
    assert len(conflicts) == 1
    assert len(called_ids) == 1
    assert len(called_clocks) == 1
    assert restored is not None
    assert int(restored.story_bible.concurrency_version) == 2
    assert state["story_bibles"] == 1
    assert state["story_bible_revisions"] == 2
    assert state["story_bible_heads"] == 1
    assert revisions == [
        (str(initial.current_revision.id), 1),
        (str(story_bible_revision_id(called_ids[0])), 2),
    ]
    assert state["head_revision_id"] == str(story_bible_revision_id(called_ids[0]))
