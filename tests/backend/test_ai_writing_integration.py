"""Real public query services and SQLite prove generation cannot write a Chapter."""

import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.ai_writing_support import FakeProvider
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_app
from tests.backend.test_novel_structure_migration import migrated_novel_structure_database_context

from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.composition import compose_ai_writing
from aiwebnovel.ai_writing.provider import LocalOpenAICompatibleProvider
from aiwebnovel.ai_writing.web import get_ai_writing_service


def test_real_read_services_generate_candidates_without_changing_any_business_row(
    tmp_path: Path,
) -> None:
    with migrated_novel_structure_database_context(tmp_path) as database:
        app = create_test_app(
            data_root=tmp_path / "app",
            database_url=str(URL.create("sqlite+pysqlite", database=database.path.as_posix())),
            environment="production",
        )
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            project = client.post("/api/v1/projects", headers=headers, json={"title": "AI fixture"})
            assert project.status_code == 201
            project_id = project.json()["project_id"]
            volume = client.post(
                f"/api/v1/projects/{project_id}/volumes",
                headers=headers,
                json={"title": "volume", "summary": "summary", "position": 1},
            )
            assert volume.status_code == 201
            volume_id = volume.json()["volume_id"]
            chapter = client.post(
                f"/api/v1/projects/{project_id}/volumes/{volume_id}/chapters",
                headers=headers,
                json={"title": "chapter", "summary": "summary", "position": 1},
            )
            assert chapter.status_code == 201
            chapter_id = chapter.json()["chapter_id"]
            base = f"/api/v1/chapters/{chapter_id}"
            original = client.put(
                base + "/content",
                headers={**headers, "If-Match": chapter.headers["ETag"]},
                json={"content": "保留正文"},
            )
            assert original.status_code == 200
            assert isinstance(app.state.ai_writing_service._provider, LocalOpenAICompatibleProvider)
            not_configured = client.post(base + "/ai/continue", headers=headers, json={})
            assert not_configured.status_code == 503
            assert not_configured.json()["error"]["message"] == "AI provider not configured"
            invalid = compose_ai_writing(
                app.state.settings,
                app.state.novel_structure_query_service,
                app.state.project_query_service,
                app.state.story_bible_query_service,
                app.state.character_query_service,
            )
            assert isinstance(invalid, AIWritingService)
            p = FakeProvider()
            real = app.state.ai_writing_service
            service = AIWritingService(real._context_builder, p)
            app.dependency_overrides[get_ai_writing_service] = lambda: service
            with closing(sqlite3.connect(database.path)) as connection:
                before = tuple(connection.iterdump())
            for op, body in (("continue", {}), ("rewrite", {"text": "需要改写\n第二段"})):
                response = client.post(base + "/ai/" + op, headers=headers, json=body)
                assert response.status_code == 200
                assert response.json()["context"]["included_sources"] == [
                    "current_chapter",
                    "volume",
                    "project",
                ]
                assert response.json()["text"] == "候选正文\n第二段"
            reread = client.get(base + "/content")
            assert reread.json() == original.json()
            assert reread.headers["ETag"] == original.headers["ETag"]
            with closing(sqlite3.connect(database.path)) as connection:
                after = tuple(connection.iterdump())
                assert before == after
                assert (
                    connection.execute("SELECT count(*) FROM chapter_revisions").fetchone()[0] == 2
                )
                assert (
                    connection.execute("SELECT concurrency_version FROM chapters").fetchone()[0]
                    == 2
                )
                assert (
                    connection.execute("SELECT revision_id FROM chapter_heads").fetchone()[0]
                    == original.json()["current_revision_id"]
                )
            assert len(p.calls) == 2
        assert app.state.ai_writing_service is None
