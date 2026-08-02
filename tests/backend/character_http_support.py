"""Shared isolated helpers for Character HTTP adapter tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_repository_support import (
    character_id,
    character_revision_id,
    project_id,
)
from tests.backend.factories import create_test_app, create_test_settings
from tests.backend.project_api_support import create_test_app_from_settings
from tests.backend.test_character_migration import migrated_character_database_context

from aiwebnovel.character.application.models import (
    CharacterListItem,
    CharacterListPage,
    CharacterListPosition,
    CharacterSnapshot,
)

ALLOWED_ORIGIN = "http://127.0.0.1:5173"
PROJECT_ID = str(project_id(1))
SECOND_PROJECT_ID = str(project_id(2))
CHARACTER_ID = str(character_id(1))
REVISION_ID = str(character_revision_id(20_001))
BASE_TIME = datetime(2026, 7, 29, 8, 9, 10, 123456, tzinfo=UTC)


def snapshot(
    *,
    version: int = 1,
    value: int = 1,
    name: str = "Character",
    role: str = "Protagonist",
    profile: str = "Initial profile",
) -> CharacterSnapshot:
    """Return one deterministic detached Character snapshot."""
    timestamp = BASE_TIME + timedelta(seconds=version - 1)
    return CharacterSnapshot(
        character_id=str(character_id(value)),
        project_id=PROJECT_ID,
        current_revision_id=str(character_revision_id(20_000 + value + version - 1)),
        revision_number=version,
        concurrency_version=version,
        name=name,
        role=role,
        profile=profile,
        created_at=BASE_TIME,
        updated_at=timestamp,
        revision_created_at=timestamp,
        head_updated_at=timestamp,
    )


def list_page(*, has_more: bool = True) -> CharacterListPage:
    """Return one deterministic Project-bound list page."""
    item = CharacterListItem(
        character_id=CHARACTER_ID,
        current_revision_id=REVISION_ID,
        revision_number=1,
        concurrency_version=1,
        name="Character",
        role="Protagonist",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    position = CharacterListPosition(
        project_id=project_id(1),
        created_at=BASE_TIME,
        character_id=character_id(1),
    )
    return CharacterListPage(
        project_id=PROJECT_ID,
        items=(item,),
        next_position=position if has_more else None,
        has_more=has_more,
    )


def isolated_app(tmp_path: Path, *, max_body_bytes: int = 1_048_576) -> FastAPI:
    """Create an unmigrated app suitable for dependency-overridden Web tests."""
    return create_test_app(
        data_root=(tmp_path / "character-api-web").resolve(),
        database_url=str(
            URL.create(
                "sqlite+pysqlite",
                database=(tmp_path / "character-api-web.sqlite3").resolve().as_posix(),
            )
        ),
        max_request_body_bytes=max_body_bytes,
    )


def issue_write_headers(client: TestClient) -> dict[str, str]:
    """Issue one local session and return its non-cookie write headers."""
    session = client.get(
        "/api/v1/security/session",
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert session.status_code == 200
    return {
        "Origin": ALLOWED_ORIGIN,
        "X-CSRF-Token": str(session.json()["csrf_token"]),
    }


@contextmanager
def migrated_character_api_app(tmp_path: Path) -> Iterator[tuple[FastAPI, Path]]:
    """Migrate one isolated database, then build the real composed API app."""
    with migrated_character_database_context(tmp_path) as database:
        settings = create_test_settings(
            data_root=(tmp_path / "character-api-storage").resolve(),
            database_url=str(
                URL.create(
                    "sqlite+pysqlite",
                    database=database.path.resolve().as_posix(),
                )
            ),
        )
        yield create_test_app_from_settings(settings), database.path
