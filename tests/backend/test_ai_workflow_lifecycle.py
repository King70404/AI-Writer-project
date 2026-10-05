"""Workflow startup recovery cannot compromise lazy startup or failure privacy."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from aiwebnovel.ai_writing.application.workflow import AIWorkflowService
from aiwebnovel.ai_writing.runtime import WorkflowRuntimeLock
from aiwebnovel.main import create_app
from aiwebnovel.storage.paths import StoragePaths

from .factories import create_test_settings
from .test_novel_structure_migration import migrated_novel_structure_database_context


def test_existing_v1_database_requires_explicit_upgrade_without_breaking_writing(
    tmp_path: Path,
) -> None:
    import sqlite3
    from contextlib import closing

    from tests.backend.character_http_support import issue_write_headers
    from tests.backend.test_novel_structure_migration import _run_alembic

    with migrated_novel_structure_database_context(tmp_path) as database:
        result = _run_alembic(database.path, "downgrade", "0006_add_chapter_manuscript_content")
        assert result.returncode == 0, result.stderr
        settings = create_test_settings(
            data_root=tmp_path / "isolated-storage",
            database_url=str(URL.create("sqlite+pysqlite", database=database.path.as_posix())),
        )
        app = create_app(settings)
        with TestClient(app) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
            headers = issue_write_headers(client)
            project = client.post("/api/v1/projects", headers=headers, json={"title": "升级前保留"})
            assert project.status_code == 201
            project_id = project.json()["project_id"]
            assert client.get(f"/api/v1/projects/{project_id}").json()["title"] == "升级前保留"
            for path in ("/api/v1/ai/models", "/api/v1/chapters/unused/ai/runs"):
                response = client.get(path)
                assert response.status_code == 503
                assert response.json()["error"]["code"] == "AI_WORKFLOW_SCHEMA_REQUIRED"
            with closing(sqlite3.connect(database.path)) as connection:
                assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
                    "0006_add_chapter_manuscript_content",
                )
        result = _run_alembic(database.path, "upgrade", "head")
        assert result.returncode == 0, result.stderr
        # A new lifespan of the same app must clear the old unavailable reason.
        with TestClient(app) as client:
            assert client.get("/api/v1/ai/models").status_code == 200
            assert client.get(f"/api/v1/projects/{project_id}").json()["title"] == "升级前保留"


def test_existing_corrupt_database_does_not_abort_live_or_expose_its_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    database = tmp_path / "private-workflow-database.sqlite3"
    database.write_bytes(b"not a sqlite database")
    settings = create_test_settings(
        data_root=tmp_path / "isolated-storage",
        database_url=str(URL.create("sqlite+pysqlite", database=database.as_posix())),
    )
    caplog.set_level(logging.ERROR)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health/live").status_code == 200
        ready = client.get("/api/v1/health/ready")
        assert ready.status_code == 503
        assert ready.json()["checks"]["database"] == "failed"
        assert database.name not in ready.text
    assert database.name not in caplog.text


def test_failed_workflow_recovery_releases_lock_and_preserves_manual_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with migrated_novel_structure_database_context(tmp_path) as database:
        settings = create_test_settings(
            data_root=tmp_path / "isolated-storage",
            database_url=str(URL.create("sqlite+pysqlite", database=database.path.as_posix())),
        )
        calls: list[bool] = []

        def unavailable(_service: AIWorkflowService) -> None:
            calls.append(True)
            raise RuntimeError("private-recovery-details")

        monkeypatch.setattr(AIWorkflowService, "recover_interrupted", unavailable)
        caplog.set_level(logging.ERROR)
        app = create_app(settings)
        with TestClient(app) as client:
            assert calls == [True]
            assert client.get("/api/v1/health/live").status_code == 200
            assert client.get("/api/v1/health/ready").status_code == 200
            assert app.state.project_command_service is not None
            assert app.state.novel_structure_command_service is not None
            assert app.state.ai_workflow_service is None
            lock = WorkflowRuntimeLock(StoragePaths.from_settings(settings).runtime_locks)
            assert lock.acquire()
            lock.close()
        assert "private-recovery-details" not in caplog.text
