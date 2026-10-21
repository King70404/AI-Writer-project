"""Real HTTP backup, verify, download and fresh-copy restore on isolated author roots."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.author_backup_support import (
    CURRENT,
    FIRST_TEXT,
    SECOND_TEXT,
    STUDIO,
    author_rows,
    build_template,
    owned_root,
    seeded_author_app,
)
from tests.backend.character_http_support import ALLOWED_ORIGIN, issue_write_headers
from tests.backend.factories import create_test_app

from aiwebnovel.backup.archive import DATABASE_MEMBER, MANIFEST_MEMBER
from aiwebnovel.storage.paths import StoragePaths

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_template(tmp_path_factory.mktemp("backup-http-template"), CURRENT)


@pytest.fixture(scope="module")
def studio_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_template(tmp_path_factory.mktemp("backup-http-studio"), STUDIO)


def _create(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post("/api/v1/backups", headers=headers, json={})
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return dict(response.json())


def test_backup_verify_download_and_restore_preserve_author_work(
    tmp_path: Path, template: Path
) -> None:
    paths = owned_root(tmp_path, template)
    with seeded_author_app(paths) as author:
        client, headers = author.client, author.headers
        created = _create(client, headers)
        backup_id = str(created["backup_id"])
        assert created["readable"] is True
        assert created["summary"] == {
            "schema_revision": CURRENT,
            "requires_upgrade": False,
            "counts": {
                "projects": 1,
                "chapters": 1,
                "chapter_revisions": 3,
                "confirmed_facts": 1,
                "workflow_runs": 1,
            },
        }

        listed = client.get("/api/v1/backups")
        assert listed.status_code == 200
        assert listed.headers["cache-control"] == "no-store"
        assert [item["backup_id"] for item in listed.json()["items"]] == [backup_id]

        verified = client.post(f"/api/v1/backups/{backup_id}/verify", headers=headers, json={})
        assert verified.status_code == 200, verified.text
        assert verified.json()["status"] == "valid"
        assert verified.json()["problem"] is None
        assert verified.json()["summary"] == created["summary"]

        download = client.get(f"/api/v1/backups/{backup_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"
        assert download.headers["cache-control"] == "no-store"
        assert (
            download.headers["content-disposition"]
            == f'attachment; filename="aiwebnovel-backup-{backup_id}.zip"'
        )
        archive_file = paths.backups / f"aiwebnovel-backup-{backup_id}.zip"
        assert download.content == archive_file.read_bytes()
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert sorted(archive.namelist()) == sorted([MANIFEST_MEMBER, DATABASE_MEMBER])

        before = author_rows(paths.database_file)
        restored = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=headers,
            json={"target_name": "恢复副本-1", "confirm_new_copy": True},
        )
        assert restored.status_code == 200, restored.text
        assert restored.json() == {
            "backup_id": backup_id,
            "target_name": "恢复副本-1",
            "summary": created["summary"],
        }
        # The current author data and backup are untouched by restore.
        assert author_rows(paths.database_file) == before
        assert archive_file.is_file()
        response_text = restored.text + verified.text + listed.text
        assert str(tmp_path) not in response_text and "作者 数据" not in response_text

    restored_paths = StoragePaths.from_root(tmp_path / "恢复副本-1")
    restored_app = create_test_app(
        data_root=restored_paths.root,
        ai_base_url="http://127.0.0.1:18123",
        ai_model="backup-test",
        environment="production",
    )
    with TestClient(restored_app) as restored_client:
        base = f"/api/v1/chapters/{author.chapter_id}"
        content = restored_client.get(base + "/content")
        assert content.status_code == 200
        assert content.json()["content"] == SECOND_TEXT
        chapter = restored_client.get(base)
        assert chapter.status_code == 200
        memory = restored_client.get(base + "/memory")
        assert memory.status_code == 200
        facts = [item for item in memory.json()["facts"] if item["id"] == author.fact_id]
        assert [item["status"] for item in facts] == ["confirmed"]
        runs = restored_client.get(base + "/ai/runs")
        assert runs.status_code == 200
        assert author.run_id in runs.text
    restored_rows = author_rows(restored_paths.database_file)
    assert restored_rows == author_rows(paths.database_file)
    # Revision history keeps every earlier saved manuscript, not only the head.
    revision_texts = {str(value) for row in restored_rows["chapter_revisions"] for value in row}
    assert {FIRST_TEXT, SECOND_TEXT} <= revision_texts


def test_restored_legacy_backup_reports_and_keeps_its_older_schema(
    tmp_path: Path, studio_template: Path
) -> None:
    paths = owned_root(tmp_path, studio_template)
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        created = _create(client, headers)
        summary = created["summary"]
        assert isinstance(summary, dict)
        assert summary["schema_revision"] == STUDIO and summary["requires_upgrade"] is True
        restored = client.post(
            f"/api/v1/backups/{created['backup_id']}/restore",
            headers=headers,
            json={"target_name": "legacy-copy", "confirm_new_copy": True},
        )
        assert restored.status_code == 200, restored.text
    restored_app = create_test_app(data_root=tmp_path / "legacy-copy", environment="production")
    with TestClient(restored_app):
        assert restored_app.state.ai_workflow_schema_required is True


def test_backup_writes_require_session_csrf_origin_and_json(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        assert client.post("/api/v1/backups", json={}).status_code == 403
        assert (
            client.post(
                "/api/v1/backups",
                headers={**headers, "Origin": "http://evil.example"},
                json={},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/backups",
                headers={"Origin": ALLOWED_ORIGIN, "X-CSRF-Token": "x" * 43},
                json={},
            ).status_code
            == 403
        )
        plain = client.post(
            "/api/v1/backups",
            headers={**headers, "Content-Type": "text/plain"},
            content=b"{}",
        )
        assert plain.status_code == 415
        extra = client.post("/api/v1/backups", headers=headers, json={"path": "/etc"})
        assert extra.status_code == 422
        assert not any(paths.backups.iterdir())
        created = _create(client, headers)
        backup_id = created["backup_id"]
        assert client.post(f"/api/v1/backups/{backup_id}/verify", json={}).status_code == 403
        assert (
            client.post(
                f"/api/v1/backups/{backup_id}/restore",
                json={"target_name": "copy", "confirm_new_copy": True},
            ).status_code
            == 403
        )
        bad_host = client.get("/api/v1/backups", headers={"Host": "evil.example"})
        assert bad_host.status_code == 400
    assert not (tmp_path / "copy").exists()


@pytest.mark.parametrize(
    ("target_name", "status", "code"),
    [
        ("../escape", 422, "VALIDATION_ERROR"),
        ("a/b", 422, "RESTORE_TARGET_INVALID"),
        ("a\\b", 422, "RESTORE_TARGET_INVALID"),
        ("..", 422, "RESTORE_TARGET_INVALID"),
        (".hidden", 422, "RESTORE_TARGET_INVALID"),
        ("trailing.", 422, "RESTORE_TARGET_INVALID"),
        ("CON", 422, "RESTORE_TARGET_INVALID"),
        ("lpt1.txt", 422, "RESTORE_TARGET_INVALID"),
        ("with space", 422, "RESTORE_TARGET_INVALID"),
        ("C:", 422, "RESTORE_TARGET_INVALID"),
        ("作者 数据", 422, "RESTORE_TARGET_INVALID"),
        ("作者数据", 422, "RESTORE_TARGET_INVALID"),
        ("occupied", 409, "RESTORE_TARGET_NOT_EMPTY"),
        ("a-file", 409, "RESTORE_TARGET_NOT_EMPTY"),
    ],
)
def test_restore_rejects_unsafe_or_occupied_targets(
    tmp_path: Path, template: Path, target_name: str, status: int, code: str
) -> None:
    paths = owned_root(tmp_path, template, name="作者数据")
    (tmp_path / "occupied").mkdir()
    (tmp_path / "occupied" / "keep.txt").write_text("作者自己的文件", encoding="utf-8")
    (tmp_path / "a-file").write_text("not a folder", encoding="utf-8")

    def outside_current_root() -> list[Path]:
        return sorted(
            path.relative_to(tmp_path)
            for path in tmp_path.rglob("*")
            if not path.is_relative_to(paths.root)
        )

    before = outside_current_root()
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        backup_id = _create(client, headers)["backup_id"]
        rows = author_rows(paths.database_file)
        response = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=headers,
            json={"target_name": target_name, "confirm_new_copy": True},
        )
        assert response.status_code == status, response.text
        if code != "VALIDATION_ERROR":
            assert response.json()["error"]["code"] == code
        assert author_rows(paths.database_file) == rows
    assert outside_current_root() == before
    assert (tmp_path / "occupied" / "keep.txt").read_text(encoding="utf-8") == "作者自己的文件"


def test_restore_into_existing_empty_folder_and_explicit_confirmation(
    tmp_path: Path, template: Path
) -> None:
    paths = owned_root(tmp_path, template)
    (tmp_path / "empty").mkdir()
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        backup_id = _create(client, headers)["backup_id"]
        unconfirmed = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=headers,
            json={"target_name": "empty", "confirm_new_copy": False},
        )
        assert unconfirmed.status_code == 422
        assert unconfirmed.json()["error"]["code"] == "RESTORE_CONFIRMATION_REQUIRED"
        assert not any((tmp_path / "empty").iterdir())
        restored = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=headers,
            json={"target_name": "empty", "confirm_new_copy": True},
        )
        assert restored.status_code == 200, restored.text
    assert (tmp_path / "empty" / "data" / "aiwebnovel.sqlite3").is_file()


@pytest.mark.parametrize(
    "backup_id",
    ["..%2F..%2Fetc", "20261020T000000Z-ZZZZZZZZZZZZ", "20261020T000000Z-000000000000"],
)
def test_unknown_or_malformed_backup_ids_are_not_found(
    tmp_path: Path, template: Path, backup_id: str
) -> None:
    paths = owned_root(tmp_path, template)
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        assert client.get(f"/api/v1/backups/{backup_id}/download").status_code == 404
        verify = client.post(f"/api/v1/backups/{backup_id}/verify", headers=headers, json={})
        assert verify.status_code == 404
        restore = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=headers,
            json={"target_name": "copy", "confirm_new_copy": True},
        )
        assert restore.status_code == 404
        # Encoded separators never reach the handler; malformed ids are rejected by it.
        assert restore.json()["error"]["code"] in {"NOT_FOUND", "BACKUP_NOT_FOUND"}
    assert not (tmp_path / "copy").exists()


def test_damaged_backup_is_reported_and_never_restored(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        backup_id = _create(client, headers)["backup_id"]
        archive = paths.backups / f"aiwebnovel-backup-{backup_id}.zip"
        with zipfile.ZipFile(archive) as source:
            manifest = source.read(MANIFEST_MEMBER)
            database = bytearray(source.read(DATABASE_MEMBER))
        database[len(database) // 2] ^= 0xFF
        archive.unlink()
        with zipfile.ZipFile(archive, "w") as rewritten:
            rewritten.writestr(MANIFEST_MEMBER, manifest)
            rewritten.writestr(DATABASE_MEMBER, bytes(database))
        verify = client.post(f"/api/v1/backups/{backup_id}/verify", headers=headers, json={})
        assert verify.status_code == 200
        assert verify.json() == {
            "backup_id": backup_id,
            "status": "corrupt",
            "problem": "BACKUP_CORRUPT",
            "summary": None,
        }
        restore = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=headers,
            json={"target_name": "copy", "confirm_new_copy": True},
        )
        assert restore.status_code == 422
        assert restore.json()["error"]["code"] == "BACKUP_CORRUPT"
        archive.write_bytes(b"not a zip archive")
        listed = client.get("/api/v1/backups").json()["items"]
        assert listed == [
            {
                "backup_id": backup_id,
                "file_bytes": len(b"not a zip archive"),
                "readable": False,
                "created_at": None,
                "summary": None,
            }
        ]
        download = client.get(f"/api/v1/backups/{backup_id}/download")
        assert download.status_code == 422
        assert download.json()["error"]["code"] == "BACKUP_CORRUPT"
    assert not (tmp_path / "copy").exists()


def test_backups_are_unavailable_for_unmanaged_or_missing_databases(
    tmp_path: Path, template: Path
) -> None:
    overridden = create_test_app(
        data_root=tmp_path / "managed",
        database_url=str(URL.create("sqlite+pysqlite", database=template.as_posix())),
        environment="production",
    )
    with TestClient(overridden) as client:
        headers = issue_write_headers(client)
        response = client.post("/api/v1/backups", headers=headers, json={})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "BACKUP_UNAVAILABLE"
        assert client.get("/api/v1/backups").status_code == 503
    empty = create_test_app(data_root=tmp_path / "fresh", environment="production")
    with TestClient(empty) as client:
        headers = issue_write_headers(client)
        response = client.post("/api/v1/backups", headers=headers, json={})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "BACKUP_UNAVAILABLE"
    assert not any((tmp_path / "fresh" / "backups").iterdir())


def test_busy_backup_service_returns_retryable_conflict(tmp_path: Path, template: Path) -> None:
    paths = owned_root(tmp_path, template)
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        service = app.state.author_backup_service
        assert service._lock.acquire(blocking=False)
        try:
            response = client.post("/api/v1/backups", headers=headers, json={})
        finally:
            service._lock.release()
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BACKUP_BUSY"
        assert response.json()["error"]["retryable"] is True


def test_unexpected_failures_map_to_safe_errors(
    tmp_path: Path, template: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aiwebnovel.backup.archive import BackupIncompatible
    from aiwebnovel.backup.service import BackupServiceError

    paths = owned_root(tmp_path, template)
    app = create_test_app(data_root=paths.root, environment="production")
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        backup_id = _create(client, headers)["backup_id"]
        service = app.state.author_backup_service

        def failed() -> None:
            raise BackupServiceError("internal detail /secret/path")

        def incompatible(*_args: object) -> None:
            raise BackupIncompatible("newer")

        monkeypatch.setattr(service, "create", failed)
        response = client.post("/api/v1/backups", headers=headers, json={})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "BACKUP_FAILED"
        assert "/secret/path" not in response.text
        monkeypatch.setattr(service, "restore_to_sibling", incompatible)
        restore = client.post(
            f"/api/v1/backups/{backup_id}/restore",
            headers=headers,
            json={"target_name": "copy", "confirm_new_copy": True},
        )
        assert restore.status_code == 409
        assert restore.json()["error"]["code"] == "BACKUP_INCOMPATIBLE"
