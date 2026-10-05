"""Real migrated SQLite and HTTP prove persistent, author-confirmed AI collaboration."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL
from tests.backend.character_http_support import issue_write_headers
from tests.backend.factories import create_test_app
from tests.backend.test_novel_structure_migration import migrated_novel_structure_database_context

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.ai_writing.application.workflow_models import WorkflowConflict
from aiwebnovel.ai_writing.persistence import repository
from aiwebnovel.ai_writing.runtime import WorkflowRuntimeLock

TEXT = "夜风吹过渡口，船夫收起船桨，望向远方的灯火。" * 10
assert 200 <= len(TEXT) <= 300


@pytest.fixture
def workflow(tmp_path: Path):
    with migrated_novel_structure_database_context(tmp_path) as database:
        settings = dict(
            data_root=tmp_path / "app",
            database_url=str(URL.create("sqlite+pysqlite", database=database.path.as_posix())),
            ai_base_url="http://127.0.0.1:18123",
            ai_model="workflow-test",
            environment="production",
        )
        app = create_test_app(**settings)
        with TestClient(app) as client:
            headers = issue_write_headers(client)
            project = client.post("/api/v1/projects", headers=headers, json={"title": "隔离AI流程"})
            assert project.status_code == 201
            project_id = project.json()["project_id"]
            volume = client.post(
                f"/api/v1/projects/{project_id}/volumes",
                headers=headers,
                json={"title": "测试卷", "summary": "", "position": 1},
            )
            assert volume.status_code == 201
            chapter = client.post(
                f"/api/v1/projects/{project_id}/volumes/{volume.json()['volume_id']}/chapters",
                headers=headers,
                json={"title": "测试章", "summary": "", "position": 1},
            )
            assert chapter.status_code == 201
            chapter_id = chapter.json()["chapter_id"]
            base = f"/api/v1/chapters/{chapter_id}"
            saved = client.put(
                base + "/content",
                headers={**headers, "If-Match": chapter.headers["ETag"]},
                json={"content": "雨😀雨。"},
            )
            assert saved.status_code == 200
            calls = []

            def provider(profile, messages, maximum, snapshot):
                calls.append((profile, messages, maximum, snapshot))
                return GeneratedText(TEXT, "workflow-test")

            service = app.state.ai_workflow_service
            assert service is not None
            service._provider = provider
            yield SimpleNamespace(
                client=client,
                headers=headers,
                app=app,
                base=base,
                chapter=chapter_id,
                project=project_id,
                db=database.path,
                service=service,
                calls=calls,
                settings=settings,
            )


def create_run(w, **values):
    result = w.client.post(
        w.base + "/ai/runs", headers=w.headers, json={"profile_id": "default-local", **values}
    )
    assert result.status_code == 201, result.text
    return result.json()


def generate(w, run):
    result = w.client.post(
        w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
    )
    assert result.status_code == 200, result.text
    return result.json()


def count_revisions(w):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute("SELECT count(*) FROM chapter_revisions").fetchone()[0]


def test_persisted_context_candidate_and_atomic_idempotent_adoption(workflow):
    w = workflow
    run = create_run(w, max_steps=2, max_output_characters=600)
    assert run["model_snapshot"]["model"] == "workflow-test"
    assert run["context"]["manifest"]["sources"][0]["references"][0][0] == w.chapter
    assert w.calls == []  # Preparing context never transmits it.
    run = generate(w, run)
    candidate = run["candidates"][0]
    assert count_revisions(w) == 2
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"
    reread = w.client.get(w.base + f"/ai/runs/{run['run_id']}")
    assert reread.json() == run
    assert (
        w.client.post(
            w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
        ).status_code
        == 409
    )
    assert len(w.calls) == 1

    def adopt():
        return w.service.adopt(w.chapter, candidate["candidate_id"], 2, "retry-key-one")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: adopt(), range(2)))
    assert all(r.candidates[0].adopted_version == 3 for r in results)
    assert count_revisions(w) == 3
    saved = w.client.get(w.base + "/content")
    assert saved.json()["content"] == "雨😀雨。\n\n" + TEXT
    manual = w.client.put(
        w.base + "/content",
        headers={**w.headers, "If-Match": saved.headers["ETag"]},
        json={"content": "作者后续手写"},
    )
    assert manual.status_code == 200
    adopt()  # A lost response retry cannot roll back later manual writing.
    assert count_revisions(w) == 4
    assert w.client.get(w.base + "/content").json()["content"] == "作者后续手写"
    assert (
        w.client.post(
            w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
        ).status_code
        == 409
    )


def test_adoption_mid_transaction_error_rolls_back_every_write(workflow, monkeypatch):
    w = workflow
    run = generate(w, create_run(w))
    candidate = run["candidates"][0]
    original = repository.adopt_workflow_content

    def failing(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected after chapter writes, before receipt")

    monkeypatch.setattr(repository, "adopt_workflow_content", failing)
    with pytest.raises(RuntimeError):
        w.service.adopt(w.chapter, candidate["candidate_id"], 2, "rollback-key")
    assert count_revisions(w) == 2
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"
    assert w.service.get(w.chapter, run["run_id"]).candidates[0].status == "pending"


def test_rewrite_uses_utf16_offsets_and_rejects_split_surrogates(workflow):
    w = workflow
    invalid = w.client.post(
        w.base + "/ai/runs",
        headers=w.headers,
        json={
            "operation": "rewrite",
            "selected_text": "雨",
            "selection_start": 2,
            "selection_end": 3,
            "max_steps": 1,
        },
    )
    assert invalid.status_code == 422
    run = generate(
        w,
        create_run(
            w,
            operation="rewrite",
            selected_text="雨",
            selection_start=3,
            selection_end=4,
            max_steps=1,
            max_output_characters=300,
        ),
    )
    candidate = run["candidates"][0]
    response = w.client.post(
        w.base + f"/ai/candidates/{candidate['candidate_id']}/adopt",
        headers={**w.headers, "If-Match": '"2"'},
        json={"idempotency_key": "utf16-adopt"},
    )
    assert response.status_code == 200, response.text
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀" + TEXT + "。"


def test_pause_during_generation_preserves_candidate_and_requires_confirmation(workflow):
    w = workflow
    run = create_run(w)

    def provider(*args):
        w.service.pause(w.chapter, run["run_id"])
        with pytest.raises(WorkflowConflict):
            w.service.resume(w.chapter, run["run_id"])
        return GeneratedText(TEXT, "workflow-test")

    w.service._provider = provider
    result = generate(w, run)
    assert result["status"] == "paused" and result["candidates"][0]["status"] == "pending"
    assert count_revisions(w) == 2
    resumed = w.service.resume(w.chapter, run["run_id"])
    assert resumed.status == "ready"
    assert count_revisions(w) == 2


@pytest.mark.parametrize("size", [199, 200, 300, 301])
def test_output_size_enforced_without_truncation_or_automatic_retry(workflow, size):
    w = workflow
    calls = []

    def provider(*args):
        calls.append(1)
        return GeneratedText("字" * size, "workflow-test")

    w.service._provider = provider
    run = create_run(w)
    result = w.client.post(
        w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
    )
    assert result.status_code == (200 if 200 <= size <= 300 else 502)
    saved = w.service.get(w.chapter, run["run_id"])
    assert len(saved.candidates) == (1 if 200 <= size <= 300 else 0)
    assert saved.generated_steps == 1 and calls == [1]
    assert count_revisions(w) == 2


def test_restart_recovery_keeps_candidates_and_never_reissues_call(workflow):
    w = workflow
    completed = generate(w, create_run(w))
    interrupted = create_run(w)
    w.service._repository.claim(w.chapter, interrupted["run_id"])
    w.service.recover_interrupted()
    assert w.service.get(w.chapter, interrupted["run_id"]).status == "interrupted"
    assert len(w.calls) == 1
    assert w.service.get(w.chapter, completed["run_id"]).candidates[0].text == TEXT
    w.app.state.ai_workflow_runtime.close()
    with TestClient(create_test_app(**w.settings)) as restarted:
        assert (
            restarted.get(w.base + f"/ai/runs/{completed['run_id']}").json()["candidates"][0][
                "text"
            ]
            == TEXT
        )
        assert (
            restarted.get(w.base + f"/ai/runs/{interrupted['run_id']}").json()["status"]
            == "interrupted"
        )


def test_runtime_lock_prevents_live_instance_recovery(tmp_path):
    first = WorkflowRuntimeLock(tmp_path)
    second = WorkflowRuntimeLock(tmp_path)
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.close()
    assert second.acquire()
    second.close()


def test_model_edit_rejects_prepared_transmission_before_network(workflow, monkeypatch):
    w = workflow
    gateway = w.app.state.model_gateway_service
    snapshot = gateway.get_profile("default-local")
    gateway.update_profile(
        snapshot.id,
        name=snapshot.name,
        kind="local",
        base_url=snapshot.base_url,
        model="changed-model",
        max_output_tokens=2048,
    )
    from aiwebnovel.ai_writing.errors import AIContextChanged

    with pytest.raises(AIContextChanged):
        gateway.generate(
            snapshot.id,
            (),
            expected_configuration=(
                snapshot.kind,
                snapshot.base_url,
                snapshot.model,
                snapshot.max_output_tokens,
            ),
        )


def test_saved_runs_restore_newest_creation_not_random_uuid_order(workflow, monkeypatch):
    from uuid import UUID

    from aiwebnovel.ai_writing.application import workflow as workflow_module

    ids = iter(
        [UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"), UUID("00000000-0000-4000-8000-000000000000")]
    )
    monkeypatch.setattr(workflow_module, "uuid4", lambda: next(ids))
    first = create_run(workflow)
    second = create_run(workflow)
    listed = workflow.client.get(workflow.base + "/ai/runs")
    assert listed.status_code == 200
    assert [run["run_id"] for run in listed.json()] == [second["run_id"], first["run_id"]]


def test_workflow_ids_cannot_read_or_adopt_another_chapters_candidates(workflow):
    w = workflow
    run = generate(w, create_run(w))
    project = w.client.post("/api/v1/projects", headers=w.headers, json={"title": "另一部小说"})
    project_id = project.json()["project_id"]
    volume = w.client.post(
        f"/api/v1/projects/{project_id}/volumes",
        headers=w.headers,
        json={"title": "卷", "summary": "", "position": 1},
    )
    chapter = w.client.post(
        f"/api/v1/projects/{project_id}/volumes/{volume.json()['volume_id']}/chapters",
        headers=w.headers,
        json={"title": "章", "summary": "", "position": 1},
    )
    assert chapter.status_code == 201
    base = f"/api/v1/chapters/{chapter.json()['chapter_id']}/ai"
    assert w.client.get(base + f"/runs/{run['run_id']}").status_code == 404
    result = w.client.post(
        base + f"/candidates/{run['candidates'][0]['candidate_id']}/adopt",
        headers={**w.headers, "If-Match": '"1"'},
        json={"idempotency_key": "cross-project"},
    )
    assert result.status_code == 404 and TEXT not in result.text
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"


def test_deleted_project_hides_all_workflow_actions_preserving_saved_drafts(workflow):
    w = workflow
    run = generate(w, create_run(w))
    with closing(sqlite3.connect(w.db)) as connection:
        before = connection.execute("SELECT * FROM ai_workflow_candidates").fetchall()
    project = w.client.get(f"/api/v1/projects/{w.project}")
    deleted = w.client.post(
        f"/api/v1/projects/{w.project}/delete",
        headers={**w.headers, "If-Match": project.headers["etag"]},
    )
    assert deleted.status_code == 200
    for suffix in ("/ai/runs", f"/ai/runs/{run['run_id']}"):
        result = w.client.get(w.base + suffix)
        assert result.status_code == 404 and TEXT not in result.text
    for action in ("generate", "pause", "resume"):
        result = w.client.post(
            w.base + f"/ai/runs/{run['run_id']}/{action}",
            headers=w.headers,
            json={},
        )
        assert result.status_code == 404 and TEXT not in result.text
    for action in ("adopt", "discard"):
        result = w.client.post(
            w.base + f"/ai/candidates/{run['candidates'][0]['candidate_id']}/{action}",
            headers={**w.headers, "If-Match": '"2"'},
            json={"idempotency_key": "deleted-adopt"} if action == "adopt" else {},
        )
        assert result.status_code == 404 and TEXT not in result.text
    assert len(w.calls) == 1 and count_revisions(w) == 2
    with closing(sqlite3.connect(w.db)) as connection:
        assert connection.execute("SELECT * FROM ai_workflow_candidates").fetchall() == before


def test_workflow_migration_roundtrip_preserves_author_content(workflow):
    from tests.backend.test_novel_structure_migration import _run_alembic

    w = workflow
    tables = ("projects", "project_revisions", "chapters", "chapter_revisions", "chapter_heads")
    with closing(sqlite3.connect(w.db)) as connection:
        before = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables
        }
    w.app.state.ai_workflow_runtime.close()
    for operation, revision in (
        ("downgrade", "0006_add_chapter_manuscript_content"),
        ("upgrade", "head"),
    ):
        result = _run_alembic(w.db, operation, revision)
        assert result.returncode == 0, result.stderr
        with closing(sqlite3.connect(w.db)) as connection:
            after = {
                table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables
            }
            assert after == before
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
