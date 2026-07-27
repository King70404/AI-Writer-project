"""Real HTTP concurrency through two Story Bible command services."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path
from threading import Barrier, Lock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from tests.backend.story_bible_http_support import (
    ALLOWED_ORIGIN,
    migrated_story_bible_api_app,
)

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.application.services import StoryBibleCommandService
from aiwebnovel.story_bible.entities import StoryBibleAggregate
from aiwebnovel.story_bible.identifiers import StoryBibleId, StoryBibleRevisionId
from aiwebnovel.story_bible.persistence.repository import (
    SqlAlchemyStoryBibleRepository,
)
from aiwebnovel.story_bible.values import StoryBibleContent, StoryBibleTitle
from aiwebnovel.story_bible.web.dependencies import get_story_bible_command_service

pytestmark = pytest.mark.integration


class BarrierRepository:
    """Synchronize only append entry, then delegate to a real independent adapter."""

    def __init__(
        self,
        repository: SqlAlchemyStoryBibleRepository,
        barrier: Barrier,
    ) -> None:
        self._repository = repository
        self._barrier = barrier

    def create(self, aggregate: StoryBibleAggregate) -> StoryBibleAggregate:
        return self._repository.create(aggregate)

    def get(self, story_bible_id: StoryBibleId) -> StoryBibleAggregate | None:
        return self._repository.get(story_bible_id)

    def get_for_project(
        self,
        project_id: ProjectId,
    ) -> StoryBibleAggregate | None:
        return self._repository.get_for_project(project_id)

    def append_revision(
        self,
        story_bible_id: StoryBibleId,
        *,
        expected_version: ConcurrencyVersion,
        title: StoryBibleTitle,
        content: StoryBibleContent,
        clock: Clock,
        revision_id_factory: Callable[[], StoryBibleRevisionId],
    ) -> StoryBibleAggregate:
        self._barrier.wait(timeout=10)
        return self._repository.append_revision(
            story_bible_id,
            expected_version=expected_version,
            title=title,
            content=content,
            clock=clock,
            revision_id_factory=revision_id_factory,
        )


class CountingClock:
    """Thread-safe call counter around one deterministic timestamp."""

    def __init__(self, value: datetime) -> None:
        self._value = value
        self._lock = Lock()
        self.calls = 0

    def __call__(self) -> datetime:
        with self._lock:
            self.calls += 1
        return self._value


class CountingRevisionIdFactory:
    """Thread-safe counter around the real Story Bible revision ID factory."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.calls = 0

    def __call__(self) -> StoryBibleRevisionId:
        with self._lock:
            self.calls += 1
        return StoryBibleRevisionId.new()


def _session(client: TestClient) -> tuple[str, str]:
    response = client.get(
        "/api/v1/security/session",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    return response.cookies["aiwebnovel_session"], str(response.json()["csrf_token"])


def test_two_http_services_produce_exactly_one_200_and_one_412(
    tmp_path: Path,
) -> None:
    with (
        migrated_story_bible_api_app(tmp_path) as (
            app,
            database_path,
        ),
        TestClient(app) as client,
    ):
        first_cookie, first_csrf = _session(client)
        project = client.post(
            "/api/v1/projects",
            headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": first_csrf},
            json={"title": "Concurrency owner"},
        )
        project_id = project.json()["project_id"]
        created = client.post(
            f"/api/v1/projects/{project_id}/story-bible",
            headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": first_csrf},
            json={"title": "Initial", "content": "Initial"},
        )
        story_bible_id = created.json()["story_bible_id"]

        second_cookie, second_csrf = _session(client)
        client.cookies.clear()
        barrier = Barrier(2)
        revision_time = datetime.fromisoformat(created.json()["updated_at"])
        first_clock = CountingClock(revision_time)
        second_clock = CountingClock(revision_time)
        first_factory = CountingRevisionIdFactory()
        second_factory = CountingRevisionIdFactory()
        first_service = StoryBibleCommandService(
            BarrierRepository(
                SqlAlchemyStoryBibleRepository(app.state.database_session_factory),
                barrier,
            ),
            first_clock,
            StoryBibleId.new,
            first_factory,
        )
        second_service = StoryBibleCommandService(
            BarrierRepository(
                SqlAlchemyStoryBibleRepository(app.state.database_session_factory),
                barrier,
            ),
            second_clock,
            StoryBibleId.new,
            second_factory,
        )

        def select_service(request: Request) -> StoryBibleCommandService:
            return (
                first_service if request.headers.get("X-Test-Worker") == "first" else second_service
            )

        app.dependency_overrides[get_story_bible_command_service] = select_service
        requests = (
            ("first", first_cookie, first_csrf, "Winner A", "FAIL-CANARY-A"),
            ("second", second_cookie, second_csrf, "Winner B", "FAIL-CANARY-B"),
        )

        def revise(values: tuple[str, str, str, str, str]):
            worker, cookie, csrf, title, content = values
            return client.put(
                f"/api/v1/story-bibles/{story_bible_id}",
                headers={
                    "Origin": ALLOWED_ORIGIN,
                    "Cookie": f"aiwebnovel_session={cookie}",
                    "X-CSRF-Token": csrf,
                    "X-Test-Worker": worker,
                    "If-Match": '"1"',
                },
                json={"title": title, "content": content},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(revise, requests))

        assert sorted(response.status_code for response in responses) == [200, 412]
        assert all(response.status_code not in {500, 503} for response in responses)
        conflict = next(response for response in responses if response.status_code == 412)
        assert conflict.json()["error"]["code"] == "STORY_BIBLE_VERSION_CONFLICT"
        assert "FAIL-CANARY-A" not in conflict.text
        assert "FAIL-CANARY-B" not in conflict.text
        winner = next(response for response in responses if response.status_code == 200)
        assert winner.headers["ETag"] == '"2"'
        assert first_clock.calls + second_clock.calls == 1
        assert first_factory.calls + second_factory.calls == 1

        final = client.get(f"/api/v1/story-bibles/{story_bible_id}")
        assert final.json() == winner.json()
        with closing(sqlite3.connect(database_path)) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM story_bible_revisions").fetchone()[0] == 2
            )
            stored = connection.execute(
                "SELECT title, content FROM story_bible_revisions "
                "ORDER BY revision_number DESC LIMIT 1"
            ).fetchone()
            head = connection.execute("SELECT revision_id FROM story_bible_heads").fetchone()[0]
        assert stored == (winner.json()["title"], winner.json()["content"])
        assert head == winner.json()["current_revision_id"]
