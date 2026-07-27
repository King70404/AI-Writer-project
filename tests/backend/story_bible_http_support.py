"""Shared isolated helpers for Story Bible HTTP adapter tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.factories import create_test_app, create_test_settings
from tests.backend.project_api_support import create_test_app_from_settings
from tests.backend.test_story_bible_migration import (
    migrated_story_bible_database_context,
)

from aiwebnovel.story_bible.application.models import StoryBibleSnapshot

ALLOWED_ORIGIN = "http://127.0.0.1:5173"
PROJECT_ID = "prj_00000000000000000000000001"
STORY_BIBLE_ID = "sbl_00000000000000000000000002"
REVISION_ID = "sbr_00000000000000000000000003"
SECOND_REVISION_ID = "sbr_00000000000000000000000004"
BASE_TIME = datetime(2026, 7, 8, 9, 10, 11, tzinfo=UTC)


def snapshot(
    *,
    version: int = 1,
    title: str = "Story Bible",
    content: str = "Initial setting",
) -> StoryBibleSnapshot:
    """Return one deterministic detached Story Bible snapshot."""
    updated_at = BASE_TIME + timedelta(seconds=version - 1)
    return StoryBibleSnapshot(
        story_bible_id=STORY_BIBLE_ID,
        project_id=PROJECT_ID,
        current_revision_id=REVISION_ID if version == 1 else SECOND_REVISION_ID,
        revision_number=version,
        concurrency_version=version,
        title=title,
        content=content,
        created_at=BASE_TIME,
        updated_at=updated_at,
        revision_created_at=updated_at,
        head_updated_at=updated_at,
    )


def isolated_app(tmp_path: Path, *, max_body_bytes: int = 1_048_576) -> FastAPI:
    """Create an unmigrated app suitable for dependency-overridden Web tests."""
    return create_test_app(
        data_root=(tmp_path / "story-bible-api-web").resolve(),
        database_url=str(
            URL.create(
                "sqlite+pysqlite",
                database=(tmp_path / "story-bible-api-web.sqlite3").resolve().as_posix(),
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
def migrated_story_bible_api_app(
    tmp_path: Path,
) -> Iterator[tuple[FastAPI, Path]]:
    """Migrate one isolated database, then build the real composed API app."""
    with migrated_story_bible_database_context(tmp_path) as database:
        settings = create_test_settings(
            data_root=(tmp_path / "story-bible-api-storage").resolve(),
            database_url=str(
                URL.create(
                    "sqlite+pysqlite",
                    database=database.path.resolve().as_posix(),
                )
            ),
        )
        yield create_test_app_from_settings(settings), database.path


__all__ = [
    "ALLOWED_ORIGIN",
    "BASE_TIME",
    "PROJECT_ID",
    "REVISION_ID",
    "SECOND_REVISION_ID",
    "STORY_BIBLE_ID",
    "isolated_app",
    "issue_write_headers",
    "migrated_story_bible_api_app",
    "snapshot",
]
