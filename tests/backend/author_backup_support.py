"""Isolated author data roots seeded through the real HTTP API for backup tests."""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_app
from tests.backend.test_novel_structure_migration import _run_alembic

from aiwebnovel.backup.service import AuthorBackupService, BackupStorageChecks
from aiwebnovel.storage.initializer import (
    initialize_storage,
    is_reparse_point,
    validate_storage_layout,
)
from aiwebnovel.storage.paths import StoragePaths

CURRENT = "0020_add_method_validation"
STUDIO = "0008_add_writing_studio"
FIRST_TEXT = "雨落渡口，船夫😀收桨。"
SECOND_TEXT = "雨落渡口，船夫😀收桨。远处灯火摇晃。"


def build_template(directory: Path, revision: str) -> Path:
    """Migrate one owned template database that tests copy instead of re-migrating."""
    database = directory / "template" / "data" / "aiwebnovel.sqlite3"
    database.parent.mkdir(parents=True)
    result = _run_alembic(database, "upgrade", revision)
    assert result.returncode == 0, result.stderr
    return database


def owned_root(tmp_path: Path, template: Path, name: str = "作者 数据") -> StoragePaths:
    """Create an isolated managed root whose database is a copy of the template."""
    paths = StoragePaths.from_root(tmp_path / name)
    initialize_storage(paths)
    shutil.copyfile(template, paths.database_file)
    return paths


def backup_service(paths: StoragePaths, **overrides: object) -> AuthorBackupService:
    return AuthorBackupService(
        paths,
        BackupStorageChecks(validate_storage_layout, is_reparse_point, initialize_storage),
        app_version="test",
        **overrides,  # type: ignore[arg-type]
    )


def author_rows(database: Path) -> dict[str, list[tuple[object, ...]]]:
    with closing(sqlite3.connect(database)) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        return {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            for table in tables
        }


@dataclass(frozen=True)
class SeededAuthor:
    client: TestClient
    headers: dict[str, str]
    paths: StoragePaths
    project_id: str
    chapter_id: str
    fact_id: str
    run_id: str


@contextmanager
def seeded_author_app(paths: StoragePaths) -> Iterator[SeededAuthor]:
    """Start the real app on the root and create text, history, a fact and a task."""
    app = create_test_app(
        data_root=paths.root,
        ai_base_url="http://127.0.0.1:18123",
        ai_model="backup-test",
        environment="production",
    )
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        project = client.post("/api/v1/projects", headers=headers, json={"title": "备份小说"})
        assert project.status_code == 201, project.text
        project_id = project.json()["project_id"]
        volume = client.post(
            f"/api/v1/projects/{project_id}/volumes",
            headers=headers,
            json={"title": "第一卷", "summary": "", "position": 1},
        )
        assert volume.status_code == 201, volume.text
        chapter = client.post(
            f"/api/v1/projects/{project_id}/volumes/{volume.json()['volume_id']}/chapters",
            headers=headers,
            json={"title": "渡口", "summary": "", "position": 1},
        )
        assert chapter.status_code == 201, chapter.text
        chapter_id = chapter.json()["chapter_id"]
        base = f"/api/v1/chapters/{chapter_id}"
        etag = chapter.headers["ETag"]
        for text in (FIRST_TEXT, SECOND_TEXT):
            saved = client.put(
                base + "/content", headers={**headers, "If-Match": etag}, json={"content": text}
            )
            assert saved.status_code == 200, saved.text
            etag = saved.headers["ETag"]
        memory = client.get(base + "/memory")
        assert memory.status_code == 200, memory.text
        created = client.post(
            base + "/memory/facts",
            headers=headers,
            json={
                "expected_version": 0,
                "source_revision": memory.json()["source_revision"],
                "title": "渡口天气",
                "text": "渡口正在下雨",
                "quote": "雨落渡口",
                "status": "pending",
            },
        )
        assert created.status_code == 201, created.text
        fact = created.json()
        confirmed = client.put(
            base + f"/memory/facts/{fact['id']}",
            headers=headers,
            json={
                **{key: fact[key] for key in ("title", "text", "quote", "source_revision")},
                "expected_version": fact["version"],
                "status": "confirmed",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        run = client.post(base + "/ai/runs", headers=headers, json={"profile_id": "default-local"})
        assert run.status_code == 201, run.text
        yield SeededAuthor(
            client,
            headers,
            paths,
            project_id,
            chapter_id,
            fact["id"],
            run.json()["run_id"],
        )
