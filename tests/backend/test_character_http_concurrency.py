"""Real HTTP Character concurrency through two independent command services."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier, Lock

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import ALLOWED_ORIGIN
from tests.backend.character_repository_support import character_id, character_revision_id
from tests.backend.factories import create_test_settings
from tests.backend.project_api_support import create_test_app_from_settings
from tests.backend.test_character_migration import migrated_character_database_context

from aiwebnovel.character.application.services import CharacterCommandService
from aiwebnovel.character.entities import CharacterAggregate
from aiwebnovel.character.identifiers import CharacterId, CharacterRevisionId
from aiwebnovel.character.persistence.repository import SqlAlchemyCharacterRepository
from aiwebnovel.character.values import CharacterName, CharacterProfile, CharacterRole
from aiwebnovel.character.web.dependencies import get_character_command_service
from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.domain.time import Clock

pytestmark = pytest.mark.integration


class BarrierRepository:
    def __init__(
        self,
        repository: SqlAlchemyCharacterRepository,
        barrier: Barrier,
    ) -> None:
        self._repository = repository
        self._barrier = barrier

    def create(self, aggregate: CharacterAggregate) -> CharacterAggregate:
        return self._repository.create(aggregate)

    def get(self, character_id: CharacterId) -> CharacterAggregate | None:
        return self._repository.get(character_id)

    def append_revision(
        self,
        character_id: CharacterId,
        *,
        expected_version: ConcurrencyVersion,
        name: CharacterName,
        role: CharacterRole,
        profile: CharacterProfile,
        clock: Clock,
        revision_id_factory: Callable[[], CharacterRevisionId],
    ) -> CharacterAggregate:
        self._barrier.wait(timeout=10)
        return self._repository.append_revision(
            character_id,
            expected_version=expected_version,
            name=name,
            role=role,
            profile=profile,
            clock=clock,
            revision_id_factory=revision_id_factory,
        )


class CountingClock:
    def __init__(self, value: datetime) -> None:
        self._value = value
        self._lock = Lock()
        self.calls = 0

    def __call__(self) -> datetime:
        with self._lock:
            self.calls += 1
        return self._value


class CountingFactory:
    def __init__(self, value: int) -> None:
        self._value = value
        self._lock = Lock()
        self.calls = 0

    def __call__(self) -> CharacterRevisionId:
        with self._lock:
            self.calls += 1
        return character_revision_id(self._value)


def _session(client: TestClient) -> tuple[str, str]:
    response = client.get(
        "/api/v1/security/session",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    return response.cookies["aiwebnovel_session"], str(response.json()["csrf_token"])


def test_two_http_clients_produce_exactly_one_200_and_one_412(tmp_path: Path) -> None:
    with migrated_character_database_context(tmp_path) as database:
        app = create_test_app_from_settings(
            create_test_settings(
                data_root=(tmp_path / "character-http-concurrency-storage").resolve(),
                database_url=str(
                    URL.create(
                        "sqlite+pysqlite",
                        database=database.path.resolve().as_posix(),
                    )
                ),
            )
        )
        with TestClient(app) as setup_client:
            cookie, csrf = _session(setup_client)
            project = setup_client.post(
                "/api/v1/projects",
                headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
                json={"title": "Concurrency owner"},
            )
            created = setup_client.post(
                f"/api/v1/projects/{project.json()['project_id']}/characters",
                headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": csrf},
                json={"name": "Initial"},
            )
            character_id_text = created.json()["character_id"]
            revision_time = datetime.fromisoformat(created.json()["updated_at"])
            barrier = Barrier(2)
            clocks = (CountingClock(revision_time), CountingClock(revision_time))
            factories = (CountingFactory(501), CountingFactory(502))
            services = tuple(
                CharacterCommandService(
                    BarrierRepository(
                        SqlAlchemyCharacterRepository(app.state.database_session_factory),
                        barrier,
                    ),
                    clocks[index],
                    lambda index=index: character_id(900 + index),
                    factories[index],
                )
                for index in range(2)
            )

            def select_service(request: Request) -> CharacterCommandService:
                return services[int(request.headers["X-Test-Worker"])]

            app.dependency_overrides[get_character_command_service] = select_service

            def revise(index: int):
                with TestClient(app) as client:
                    return client.put(
                        f"/api/v1/characters/{character_id_text}",
                        headers={
                            "Origin": ALLOWED_ORIGIN,
                            "Cookie": f"aiwebnovel_session={cookie}",
                            "X-CSRF-Token": csrf,
                            "X-Test-Worker": str(index),
                            "If-Match": '"1"',
                        },
                        json={
                            "name": f"Winner {index}",
                            "role": "",
                            "profile": f"FAIL-CANARY-{index}",
                        },
                    )

            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(revise, range(2)))

            assert sorted(response.status_code for response in responses) == [200, 412]
            assert all(response.status_code not in {500, 503} for response in responses)
            conflict = next(response for response in responses if response.status_code == 412)
            assert conflict.json()["error"]["code"] == "CHARACTER_VERSION_CONFLICT"
            assert "FAIL-CANARY" not in conflict.text
            winner = next(response for response in responses if response.status_code == 200)
            assert winner.headers["ETag"] == '"2"'
            assert sum(clock.calls for clock in clocks) == 1
            assert sum(factory.calls for factory in factories) == 1
