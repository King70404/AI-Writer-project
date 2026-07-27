"""Real migrated-repository integration for Story Bible application use cases."""

from datetime import timedelta
from pathlib import Path

import pytest
from tests.backend.story_bible_repository_support import (
    BASE_TIME,
    create_project,
    project_id,
    repository_database,
    story_bible_id,
    story_bible_revision_id,
)

from aiwebnovel.story_bible.application.commands import (
    CreateStoryBibleCommand,
    ReviseStoryBibleCommand,
)
from aiwebnovel.story_bible.application.queries import (
    GetStoryBibleForProjectQuery,
    GetStoryBibleQuery,
)
from aiwebnovel.story_bible.application.services import (
    StoryBibleCommandService,
    StoryBibleQueryService,
)

pytestmark = pytest.mark.integration


def test_real_repository_create_read_revise_and_latest_read_flow(
    tmp_path: Path,
) -> None:
    with repository_database(tmp_path) as database:
        owner = create_project(database)
        command_service = StoryBibleCommandService(
            database.repository,
            lambda: BASE_TIME,
            lambda: story_bible_id(101),
            lambda: story_bible_revision_id(201),
        )
        query_service = StoryBibleQueryService(database.repository)

        created = command_service.create_story_bible(
            CreateStoryBibleCommand(
                project_id=str(owner.project.id),
                title="  Initial Bible  ",
                content="first\r\nsnapshot",
            )
        )
        by_id = query_service.get_story_bible(GetStoryBibleQuery(created.story_bible_id))
        by_project = query_service.get_story_bible_for_project(
            GetStoryBibleForProjectQuery(str(owner.project.id))
        )

        revision_factory_calls: list[int] = []

        def revision_factory():
            revision_factory_calls.append(1)
            return story_bible_revision_id(202)

        revise_service = StoryBibleCommandService(
            database.repository,
            lambda: BASE_TIME + timedelta(seconds=1),
            lambda: story_bible_id(999),
            revision_factory,
        )
        revised = revise_service.revise_story_bible(
            ReviseStoryBibleCommand(
                story_bible_id=created.story_bible_id,
                expected_version=1,
                title="Revised Bible",
                content="complete replacement",
            )
        )
        latest = query_service.get_story_bible(GetStoryBibleQuery(created.story_bible_id))

        with database.engine.connect() as connection:
            counts = {
                table: connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar_one()
                for table in (
                    "story_bibles",
                    "story_bible_revisions",
                    "story_bible_heads",
                )
            }
            revisions = connection.exec_driver_sql(
                "SELECT id, revision_number, title, content "
                "FROM story_bible_revisions "
                "WHERE story_bible_id = ? ORDER BY revision_number",
                (created.story_bible_id,),
            ).all()
            head_revision_id = connection.exec_driver_sql(
                "SELECT revision_id FROM story_bible_heads WHERE story_bible_id = ?",
                (created.story_bible_id,),
            ).scalar_one()
            project_state = connection.exec_driver_sql(
                "SELECT concurrency_version FROM projects WHERE id = ?",
                (str(owner.project.id),),
            ).scalar_one()
            project_revision_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM project_revisions WHERE project_id = ?",
                (str(owner.project.id),),
            ).scalar_one()

    assert created.revision_number == created.concurrency_version == 1
    assert created.project_id == str(project_id(1))
    assert created.title == "Initial Bible"
    assert created.content == "first\nsnapshot"
    assert by_id == created
    assert by_project == created
    assert revised.revision_number == revised.concurrency_version == 2
    assert revised.title == "Revised Bible"
    assert revised.content == "complete replacement"
    assert latest == revised
    assert revision_factory_calls == [1]
    assert counts == {
        "story_bibles": 1,
        "story_bible_revisions": 2,
        "story_bible_heads": 1,
    }
    assert revisions == [
        (str(story_bible_revision_id(201)), 1, "Initial Bible", "first\nsnapshot"),
        (
            str(story_bible_revision_id(202)),
            2,
            "Revised Bible",
            "complete replacement",
        ),
    ]
    assert head_revision_id == str(story_bible_revision_id(202))
    assert project_state == 1
    assert project_revision_count == 1
    assert latest.title == "Revised Bible"
