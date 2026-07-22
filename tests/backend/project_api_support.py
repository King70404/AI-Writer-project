"""Shared isolated helpers for Project HTTP adapter tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.factories import create_test_app, create_test_settings
from tests.backend.test_project_migration import migrated_project_database_context

from aiwebnovel.project.application.models import ProjectSnapshot

ALLOWED_ORIGIN = "http://127.0.0.1:5173"
PROJECT_ID = "prj_00000000000000000000000001"
REVISION_ID = "prv_00000000000000000000000002"
BASE_TIME = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)


def snapshot(*, version: int = 1, revision_number: int = 1) -> ProjectSnapshot:
    """Return one deterministic detached Project snapshot."""
    return ProjectSnapshot(
        project_id=PROJECT_ID,
        current_revision_id=REVISION_ID,
        revision_number=revision_number,
        concurrency_version=version,
        title="Project title",
        description="Project description",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        revision_created_at=BASE_TIME,
        head_updated_at=BASE_TIME,
    )


def isolated_app(tmp_path: Path, *, max_body_bytes: int = 1_048_576) -> FastAPI:
    """Create an unmigrated app suitable for dependency-overridden Web tests."""
    return create_test_app(
        data_root=(tmp_path / "project-api-web").resolve(),
        database_url=str(
            URL.create(
                "sqlite+pysqlite",
                database=(tmp_path / "project-api-web.sqlite3").resolve().as_posix(),
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
def migrated_api_app(tmp_path: Path) -> Iterator[tuple[FastAPI, Path]]:
    """Migrate one isolated database, then build the real composed API app."""
    with migrated_project_database_context(tmp_path) as database:
        settings = create_test_settings(
            data_root=(tmp_path / "project-api-storage").resolve(),
            database_url=str(
                URL.create("sqlite+pysqlite", database=database.path.resolve().as_posix())
            ),
        )
        yield create_test_app_from_settings(settings), database.path


def create_test_app_from_settings(settings: object) -> FastAPI:
    """Keep the support module's Settings-to-app construction explicit."""
    from aiwebnovel.core.config import Settings
    from aiwebnovel.main import create_app

    if not isinstance(settings, Settings):
        raise TypeError("settings must be Settings")
    return create_app(settings)
