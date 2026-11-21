"""Real migrated SQLite downloads prove byte format and business-state immutability."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.ai_workflow_contract_support import (
    AI_WORKFLOW_OPERATIONS,
    BACKUP_OPERATIONS,
    CANDIDATE_BUDGET_OPERATIONS,
    HANDOFF_OPERATIONS,
    IMPORT_OPERATIONS,
    STORY_CONTROL_OPERATIONS,
    STORY_MEMORY_OPERATIONS,
    USAGE_OPERATIONS,
    WORKBENCH_OPERATIONS,
    WRITING_JOB_OPERATIONS,
    WRITING_PREPARATION_OPERATIONS,
)
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_app
from tests.backend.test_novel_structure_migration import migrated_novel_structure_database_context

from aiwebnovel.novel_structure.application.services import NovelStructureQueryService
from aiwebnovel.novel_structure.errors import NovelStructureRepositoryError
from aiwebnovel.novel_structure.web.dependencies import get_query_service
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.web.dependencies import get_project_query_service


@pytest.mark.parametrize("shape", ["no_volumes", "empty_volume", "chapters"])
def test_real_export_is_utf8_current_heads_and_changes_no_database_rows(
    tmp_path: Path, shape: str
) -> None:
    with migrated_novel_structure_database_context(tmp_path) as database:
        app = create_test_app(
            data_root=tmp_path / "app",
            database_url=str(URL.create("sqlite+pysqlite", database=database.path.as_posix())),
            environment="production",
        )
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            project = client.post("/api/v1/projects", headers=headers, json={"title": "旧题"})
            assert project.status_code == 201
            pid = project.json()["project_id"]
            revised = client.put(
                f"/api/v1/projects/{pid}",
                headers={**headers, "If-Match": project.headers["ETag"]},
                json={"title": "归途", "description": "不导出的项目简介"},
            )
            assert revised.status_code == 200
            expected = "《归途》\n"
            if shape != "no_volumes":
                # Deliberately create in descending position order.
                for position in (2, 1):
                    volume = client.post(
                        f"/api/v1/projects/{pid}/volumes",
                        headers=headers,
                        json={
                            "title": f"卷题{position}",
                            "summary": "不导出的卷梗概",
                            "position": position,
                        },
                    )
                    assert volume.status_code == 201
                    if shape == "chapters" and position == 1:
                        vid = volume.json()["volume_id"]
                        for chapter_position in (2, 1):
                            chapter = client.post(
                                f"/api/v1/projects/{pid}/volumes/{vid}/chapters",
                                headers=headers,
                                json={
                                    "title": f"章题{chapter_position}",
                                    "summary": "不导出的章梗概",
                                    "position": chapter_position,
                                },
                            )
                            assert chapter.status_code == 201
                            if chapter_position == 1:
                                path = f"/api/v1/chapters/{chapter.json()['chapter_id']}/content"
                                old = client.put(
                                    path,
                                    headers={**headers, "If-Match": chapter.headers["ETag"]},
                                    json={"content": "旧正文不导出"},
                                )
                                assert old.status_code == 200
                                current = client.put(
                                    path,
                                    headers={**headers, "If-Match": old.headers["ETag"]},
                                    json={"content": "雨落长街。\r\n灯还亮着。"},
                                )
                                assert current.status_code == 200
                expected = "《归途》\n\n第1卷 卷题1\n\n第2卷 卷题2\n"
                if shape == "chapters":
                    expected = "《归途》\n\n第1卷 卷题1\n\n第1章 章题1\n\n雨落长街。\n灯还亮着。\n\n第2章 章题2\n\n\n\n第2卷 卷题2\n"
            with closing(sqlite3.connect(database.path)) as connection:
                before = tuple(connection.iterdump())
                assert (
                    connection.execute(
                        "select count(*) from sqlite_master where type='trigger'"
                    ).fetchone()[0]
                    == 41
                )
            files_before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
            for _ in range(2):
                response = client.get(f"/api/v1/projects/{pid}/export.txt")
                assert response.status_code == 200
                assert response.content == expected.encode("utf-8")
                assert response.headers["content-type"] == "text/plain; charset=utf-8"
                assert response.headers["content-disposition"] == 'attachment; filename="novel.txt"'
                assert response.headers["cache-control"] == "no-store"
                assert b"\r" not in response.content
            assert files_before == {
                p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()
            }
            with closing(sqlite3.connect(database.path)) as connection:
                assert before == tuple(connection.iterdump())
            missing = client.get("/api/v1/projects/prj_01ARZ3NDEKTSV4RRFFQ69G5FAV/export.txt")
            assert missing.status_code == 404
            assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_openapi_preserves_m6_with_exact_export_and_project_deletion_additions(
    tmp_path: Path,
) -> None:
    baseline = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/M6_BASELINE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    app = create_test_app(data_root=tmp_path / "app", environment="production")
    schema = app.openapi()
    operations = {
        (method.upper(), path)
        for path, methods in schema["paths"].items()
        for method in methods
        if method in {"get", "post", "put", "patch", "delete"}
    }
    old = {(item["method"], item["path"]) for item in baseline["production_api_operations"]}
    assert len(old) == 36
    assert len(operations) == 147
    assert len(AI_WORKFLOW_OPERATIONS) == 14
    assert len(WRITING_PREPARATION_OPERATIONS) == 22
    assert len(BACKUP_OPERATIONS) == 5
    assert len(WORKBENCH_OPERATIONS) == 6
    assert len(USAGE_OPERATIONS) == 1
    assert len(CANDIDATE_BUDGET_OPERATIONS) == 8
    assert len(STORY_CONTROL_OPERATIONS) == 28
    assert operations >= AI_WORKFLOW_OPERATIONS
    assert operations >= (
        WRITING_PREPARATION_OPERATIONS
        | STORY_MEMORY_OPERATIONS
        | BACKUP_OPERATIONS
        | WORKBENCH_OPERATIONS
        | USAGE_OPERATIONS
        | CANDIDATE_BUDGET_OPERATIONS
        | STORY_CONTROL_OPERATIONS
        | IMPORT_OPERATIONS
        | HANDOFF_OPERATIONS
        | WRITING_JOB_OPERATIONS
    )
    assert old < operations
    assert operations - AI_WORKFLOW_OPERATIONS - (
        WRITING_PREPARATION_OPERATIONS
        | STORY_MEMORY_OPERATIONS
        | BACKUP_OPERATIONS
        | WORKBENCH_OPERATIONS
        | USAGE_OPERATIONS
        | CANDIDATE_BUDGET_OPERATIONS
        | STORY_CONTROL_OPERATIONS
        | IMPORT_OPERATIONS
        | HANDOFF_OPERATIONS
        | WRITING_JOB_OPERATIONS
    ) - old == {
        ("GET", "/api/v1/projects/{project_id}/export.txt"),
        ("POST", "/api/v1/projects/{project_id}/delete"),
    }
    assert (
        "text/plain"
        in schema["paths"]["/api/v1/projects/{project_id}/export.txt"]["get"]["responses"]["200"][
            "content"
        ]
    )


def test_export_maps_structure_failure_without_leaking_internals(tmp_path: Path) -> None:
    app = create_test_app(data_root=tmp_path / "app")
    projects = Mock(spec=ProjectQueryService)
    structure = Mock(spec=NovelStructureQueryService)
    structure.list_volumes.side_effect = NovelStructureRepositoryError()
    app.dependency_overrides[get_project_query_service] = lambda: projects
    app.dependency_overrides[get_query_service] = lambda: structure
    with TestClient(app) as client:
        response = client.get("/api/v1/projects/prj_01ARZ3NDEKTSV4RRFFQ69G5FAV/export.txt")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "NOVEL_STRUCTURE_PERSISTENCE_UNAVAILABLE"
        assert client.get("/api/v1/projects/invalid/export.txt").status_code == 422
