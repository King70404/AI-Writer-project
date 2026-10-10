"""An existing author database can explicitly enable AI without restarting the app."""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import aiwebnovel.main as app_module
from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.ai_writing.setup_web import AIWorkflowSetupService
from aiwebnovel.core.errors import AppError
from aiwebnovel.db.ai_workflow_upgrade import (
    AIWorkflowUpgradeBusy,
    AIWorkflowUpgradeFailed,
    AIWorkflowUpgradeUnsupported,
)
from aiwebnovel.storage.initializer import initialize_storage
from aiwebnovel.storage.paths import StoragePaths

from .character_http_support import issue_write_headers
from .factories import create_test_settings
from .test_novel_structure_migration import _run_alembic

SETUP = "/api/v1/ai/workflow-setup/upgrade"


@contextmanager
def old_app(tmp_path: Path):
    settings = create_test_settings(data_root=tmp_path / "author-fixture", database_url=None)
    paths = StoragePaths.from_settings(settings)
    initialize_storage(paths)
    result = _run_alembic(paths.database_file, "upgrade", "0006_add_chapter_manuscript_content")
    assert result.returncode == 0, result.stderr
    app = app_module.create_app(settings)
    with TestClient(app) as client:
        yield app, client, paths, issue_write_headers(client)


def test_old_database_author_can_upgrade_save_model_generate_and_adopt_without_restart(tmp_path):
    with old_app(tmp_path) as (app, client, paths, headers):
        assert client.get("/api/v1/ai/models").status_code == 503
        project = client.post("/api/v1/projects", headers=headers, json={"title": "升级保留正文"})
        assert project.status_code == 201
        project_path = "/api/v1/projects/" + project.json()["project_id"]
        volume = client.post(
            project_path + "/volumes",
            headers=headers,
            json={"title": "卷", "summary": "", "position": 1},
        )
        assert volume.status_code == 201
        chapter = client.post(
            project_path + "/volumes/" + volume.json()["volume_id"] + "/chapters",
            headers=headers,
            json={"title": "章", "summary": "", "position": 1},
        )
        assert chapter.status_code == 201
        chapter_path = "/api/v1/chapters/" + chapter.json()["chapter_id"]
        saved = client.put(
            chapter_path + "/content",
            headers={**headers, "If-Match": chapter.headers["ETag"]},
            json={"content": "原有正文😀不会丢失。"},
        )
        assert saved.status_code == 200
        for payload in (
            {},
            {"confirm_backup": False},
            {"confirm_backup": "true"},
            {"confirm_backup": True, "root": "elsewhere"},
        ):
            assert client.post(SETUP, headers=headers, json=payload).status_code == 422
        assert client.post(SETUP, json={"confirm_backup": True}).status_code in (401, 403)
        assert not list(paths.backups.iterdir())
        assert client.get("/api/v1/ai/models").status_code == 503
        upgraded = client.post(SETUP, headers=headers, json={"confirm_backup": True})
        assert upgraded.status_code == 200, upgraded.text
        assert upgraded.json() == {"status": "ready"}
        assert upgraded.headers["Cache-Control"] == "no-store"
        assert client.get(chapter_path + "/content").json() == saved.json()
        backups = list(paths.backups.glob("*.sqlite3"))
        assert len(backups) == 1
        with closing(sqlite3.connect(backups[0])) as backup:
            assert backup.execute("PRAGMA quick_check").fetchone() == ("ok",)
            assert backup.execute("SELECT version_num FROM alembic_version").fetchone() == (
                "0006_add_chapter_manuscript_content",
            )
            assert backup.execute("SELECT COUNT(*) FROM chapter_revisions").fetchone()[0] == 2
        model = client.post(
            "/api/v1/ai/models",
            headers=headers,
            json={
                "name": "升级后模型",
                "kind": "local",
                "base_url": "http://127.0.0.1:18123",
                "model": "isolated-model",
            },
        )
        assert model.status_code == 201, model.text
        assert model.json() in client.get("/api/v1/ai/models").json()["items"]
        created = client.post(
            chapter_path + "/ai/runs",
            headers=headers,
            json={"profile_id": model.json()["id"], "max_steps": 1},
        )
        assert created.status_code == 201, created.text
        text = "隔离候选文本。" * 30
        app.state.ai_workflow_service._provider = lambda *_: GeneratedText(text, "isolated-model")
        generated = client.post(
            chapter_path + "/ai/runs/" + created.json()["run_id"] + "/generate",
            headers=headers,
            json={},
        )
        assert generated.status_code == 200, generated.text
        assert client.get(chapter_path + "/content").json() == saved.json()
        candidate = generated.json()["candidates"][0]["candidate_id"]
        adopted = client.post(
            chapter_path + "/ai/candidates/" + candidate + "/adopt",
            headers={**headers, "If-Match": saved.headers["ETag"]},
            json={"idempotency_key": "upgrade-adoption"},
        )
        assert adopted.status_code == 200, adopted.text
        assert text in client.get(chapter_path + "/content").json()["content"]
        assert client.post(SETUP, headers=headers, json={"confirm_backup": True}).status_code == 200
        assert list(paths.backups.glob("*.sqlite3")) == backups


def test_activation_failure_keeps_backup_and_can_retry_without_second_migration(
    tmp_path, monkeypatch
):
    with old_app(tmp_path) as (_, client, paths, headers):
        original = app_module.compose_ai_workflow
        monkeypatch.setattr(app_module, "compose_ai_workflow", lambda *_: None)
        failed = client.post(SETUP, headers=headers, json={"confirm_backup": True})
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "AI_WORKFLOW_UPGRADE_FAILED"
        backups = list(paths.backups.glob("*.sqlite3"))
        assert len(backups) == 1
        monkeypatch.setattr(app_module, "compose_ai_workflow", original)
        assert client.post(SETUP, headers=headers, json={"confirm_backup": True}).status_code == 200
        assert client.get("/api/v1/ai/models").status_code == 200
        assert list(paths.backups.glob("*.sqlite3")) == backups


def test_upgrade_rejects_overlapping_calls_and_releases_lock_on_failure():
    def reentrant():
        with pytest.raises(AppError, match="already running"):
            service.enable()
        raise RuntimeError("controlled failure")

    service = AIWorkflowSetupService(reentrant)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="controlled failure"):
            service.enable()


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (AIWorkflowUpgradeBusy, 409, "AI_WORKFLOW_UPGRADE_BUSY"),
        (AIWorkflowUpgradeUnsupported, 409, "AI_WORKFLOW_UPGRADE_UNSUPPORTED"),
        (AIWorkflowUpgradeFailed, 503, "AI_WORKFLOW_UPGRADE_FAILED"),
    ],
)
def test_upgrade_failures_are_recoverable_and_do_not_expose_internal_details(
    tmp_path, monkeypatch, failure, status, code
):
    with old_app(tmp_path) as (_, client, paths, headers):

        def fail(*_):
            raise failure("private database detail")

        monkeypatch.setattr(app_module, "upgrade_ai_workflow_database", fail)
        result = client.post(SETUP, headers=headers, json={"confirm_backup": True})
        assert result.status_code == status
        assert result.json()["error"]["code"] == code
        assert "private database detail" not in result.text
        assert client.get("/api/v1/ai/models").status_code == 503
        assert not list(paths.backups.iterdir())


def test_upgrade_unavailable_and_security_failures_do_not_touch_database(tmp_path):
    with old_app(tmp_path) as (app, client, paths, headers):
        assert (
            client.post(
                SETUP,
                headers={**headers, "Origin": "https://untrusted.example"},
                json={"confirm_backup": True},
            ).status_code
            == 403
        )
        assert (
            client.post(
                SETUP,
                headers={**headers, "Content-Type": "text/plain"},
                content='{"confirm_backup":true}',
            ).status_code
            == 415
        )
        app.state.ai_workflow_setup_service = None
        result = client.post(SETUP, headers=headers, json={"confirm_backup": True})
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "AI_WORKFLOW_UPGRADE_FAILED"
        assert not list(paths.backups.iterdir())


def test_activation_exception_is_private_and_retryable(tmp_path, monkeypatch):
    with old_app(tmp_path) as (_, client, paths, headers):
        original = app_module.compose_ai_workflow

        def fail(*_):
            raise RuntimeError("private activation detail")

        monkeypatch.setattr(app_module, "compose_ai_workflow", fail)
        result = client.post(SETUP, headers=headers, json={"confirm_backup": True})
        assert result.status_code == 503
        assert "private activation detail" not in result.text
        monkeypatch.setattr(app_module, "compose_ai_workflow", original)
        assert client.post(SETUP, headers=headers, json={"confirm_backup": True}).status_code == 200
        assert len(list(paths.backups.glob("*.sqlite3"))) == 1
