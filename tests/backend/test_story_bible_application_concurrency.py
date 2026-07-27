"""Two-service Story Bible application concurrency over real SQLite."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from tests.backend.story_bible_repository_support import (
    BASE_TIME,
    create_project,
    later,
    repository_database,
    story_bible_id,
    story_bible_revision_id,
)

from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)
from aiwebnovel.story_bible.application.models import StoryBibleSnapshot
from aiwebnovel.story_bible.application.services import StoryBibleCommandService
from aiwebnovel.story_bible.persistence.repository import (
    SqlAlchemyStoryBibleRepository,
)

pytestmark = pytest.mark.integration


def test_two_command_services_produce_one_snapshot_and_one_conflict(
    tmp_path: Path,
) -> None:
    barrier = Barrier(2)
    clock_calls: list[list[int]] = [[], []]
    factory_calls: list[list[int]] = [[], []]

    with repository_database(tmp_path) as database:
        owner = create_project(database)
        creator = StoryBibleCommandService(
            database.repository,
            lambda: BASE_TIME,
            lambda: story_bible_id(301),
            lambda: story_bible_revision_id(401),
        )
        initial = creator.create_story_bible(
            CreateStoryBibleCommand(
                project_id=str(owner.project.id),
                title="Initial",
                content="initial content",
            )
        )
        repositories = (
            SqlAlchemyStoryBibleRepository(database.session_factory),
            SqlAlchemyStoryBibleRepository(database.session_factory),
        )

        def make_service(index: int) -> StoryBibleCommandService:
            def clock():
                clock_calls[index].append(index)
                return later()

            def revision_factory():
                factory_calls[index].append(index)
                return story_bible_revision_id(402 + index)

            return StoryBibleCommandService(
                repositories[index],
                clock,
                lambda: story_bible_id(900 + index),
                revision_factory,
            )

        services = (make_service(0), make_service(1))

        def revise(index: int) -> StoryBibleSnapshot:
            barrier.wait()
            return services[index].revise_story_bible(
                ReviseStoryBibleCommand(
                    story_bible_id=initial.story_bible_id,
                    expected_version=1,
                    title=f"Candidate {index}",
                    content=f"candidate content {index}",
                )
            )

        outcomes: list[StoryBibleSnapshot | Exception] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(revise, index) for index in range(2)]
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=10))
                except Exception as exc:  # noqa: BLE001 - exact outcomes asserted
                    outcomes.append(exc)

        with database.engine.connect() as connection:
            revisions = connection.exec_driver_sql(
                "SELECT id, revision_number, title, content "
                "FROM story_bible_revisions "
                "WHERE story_bible_id = ? ORDER BY revision_number",
                (initial.story_bible_id,),
            ).all()
            head_revision_id = connection.exec_driver_sql(
                "SELECT revision_id FROM story_bible_heads WHERE story_bible_id = ?",
                (initial.story_bible_id,),
            ).scalar_one()

    successes = [item for item in outcomes if type(item) is StoryBibleSnapshot]
    conflicts = [item for item in outcomes if type(item) is ConcurrencyConflict]
    assert len(successes) == 1
    assert len(conflicts) == 1
    success = successes[0]
    assert isinstance(success, StoryBibleSnapshot)
    assert success.concurrency_version == success.revision_number == 2
    winner = int(success.title.rsplit(" ", maxsplit=1)[1])
    loser = 1 - winner
    assert clock_calls[winner] == [winner]
    assert factory_calls[winner] == [winner]
    assert clock_calls[loser] == []
    assert factory_calls[loser] == []
    assert revisions == [
        (str(story_bible_revision_id(401)), 1, "Initial", "initial content"),
        (
            str(story_bible_revision_id(402 + winner)),
            2,
            f"Candidate {winner}",
            f"candidate content {winner}",
        ),
    ]
    assert head_revision_id == str(story_bible_revision_id(402 + winner))
    assert f"Candidate {loser}" not in {row[2] for row in revisions}
    assert f"candidate content {loser}" not in {row[3] for row in revisions}
    assert all(str(story_bible_revision_id(402 + loser)) != row[0] for row in revisions)
