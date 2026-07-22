"""Real HTTP concurrency with two sessions and one migrated SQLite database."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import ALLOWED_ORIGIN, migrated_api_app

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.application.services import ProjectCommandService
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.values import ProjectDescription, ProjectTitle
from aiwebnovel.project.web.dependencies import get_project_command_service

pytestmark = pytest.mark.integration


class BarrierRepository:
    """Synchronize only revision appends before delegating to the real adapter."""

    def __init__(self, repository: SqlAlchemyProjectRepository, barrier: Barrier) -> None:
        self._repository = repository
        self._barrier = barrier

    def create(self, aggregate: ProjectAggregate) -> ProjectAggregate:
        return self._repository.create(aggregate)

    def get(self, project_id: ProjectId) -> ProjectAggregate | None:
        return self._repository.get(project_id)

    def append_revision(
        self,
        project_id: ProjectId,
        expected_version: ConcurrencyVersion,
        title: ProjectTitle,
        description: ProjectDescription,
        *,
        clock: Clock | None = None,
        revision_id_factory: Callable[[], ProjectRevisionId] = ProjectRevisionId.new,
    ) -> ProjectAggregate:
        self._barrier.wait(timeout=10)
        return self._repository.append_revision(
            project_id,
            expected_version,
            title,
            description,
            clock=clock,
            revision_id_factory=revision_id_factory,
        )


def _issue_session(client: TestClient) -> tuple[str, str]:
    response = client.get(
        "/api/v1/security/session",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    return response.cookies["aiwebnovel_session"], str(response.json()["csrf_token"])


def test_two_http_sessions_produce_exactly_one_200_and_one_412(tmp_path: Path) -> None:
    with migrated_api_app(tmp_path) as (app, database_path), TestClient(app) as client:
        first_cookie, first_csrf = _issue_session(client)
        created = client.post(
            "/api/v1/projects",
            headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": first_csrf},
            json={"title": "Initial"},
        )
        assert created.status_code == 201
        project_id = created.json()["project_id"]

        second_cookie, second_csrf = _issue_session(client)
        client.cookies.clear()
        barrier = Barrier(2)
        repository = SqlAlchemyProjectRepository(app.state.database_session_factory)
        service = ProjectCommandService(BarrierRepository(repository, barrier))
        app.dependency_overrides[get_project_command_service] = lambda: service

        requests = (
            (first_cookie, first_csrf, "Concurrent A", "CANARY-A"),
            (second_cookie, second_csrf, "Concurrent B", "CANARY-B"),
        )

        def revise(values: tuple[str, str, str, str]):
            cookie, csrf, title, description = values
            return client.put(
                f"/api/v1/projects/{project_id}",
                headers={
                    "Origin": ALLOWED_ORIGIN,
                    "Cookie": f"aiwebnovel_session={cookie}",
                    "X-CSRF-Token": csrf,
                    "If-Match": '"1"',
                },
                json={"title": title, "description": description},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(revise, requests))

        assert sorted(response.status_code for response in responses) == [200, 412]
        assert all(response.status_code != 500 for response in responses)
        conflict = next(response for response in responses if response.status_code == 412)
        assert conflict.json()["error"]["code"] == "PROJECT_VERSION_CONFLICT"
        assert "CANARY-A" not in conflict.text
        assert "CANARY-B" not in conflict.text

        final = client.get(f"/api/v1/projects/{project_id}")
        assert final.status_code == 200
        assert final.headers["ETag"] == '"2"'
        with closing(sqlite3.connect(database_path)) as connection:
            assert connection.execute("SELECT COUNT(*) FROM project_revisions").fetchone()[0] == 2
            head = connection.execute("SELECT revision_id FROM project_heads").fetchone()[0]
        assert head == final.json()["current_revision_id"]
