"""Real SQLite and HTTP verify author authority, recall, source invalidation and review sends."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event
from uuid import uuid4

import pytest
from tests.backend.test_ai_workflow import workflow

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.ai_writing.errors import AIProviderTimeout
from aiwebnovel.story_memory.models import Fact as MemoryFact
from aiwebnovel.story_memory.models import MemoryConflict, Review

__all__ = ["workflow"]


def workspace(w, chapter=None):
    response = w.client.get(f"/api/v1/chapters/{chapter or w.chapter}/memory")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def fact(w, **changes):
    data = {
        "expected_version": 0,
        "source_revision": workspace(w)["source_revision"],
        "title": "渡口天气",
        "text": "渡口正在下雨",
        "quote": "雨😀雨。",
        "status": "pending",
        **changes,
    }
    response = w.client.post(w.base + "/memory/facts", headers=w.headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def confirm(w, current, **changes):
    data = {key: current[key] for key in ("title", "text", "quote", "source_revision")}
    data.update(expected_version=current["version"], status="confirmed", **changes)
    response = w.client.put(w.base + f"/memory/facts/{current['id']}", headers=w.headers, json=data)
    assert response.status_code == 200, response.text
    return response.json()


def next_chapter(w):
    content = w.client.get(w.base + "/content").json()
    response = w.client.post(
        f"/api/v1/projects/{w.project}/volumes/{content['volume_id']}/chapters",
        headers=w.headers,
        json={"title": "后文章节", "summary": "", "position": 2},
    )
    assert response.status_code == 201, response.text
    chapter = response.json()["chapter_id"]
    response = w.client.put(
        f"/api/v1/chapters/{chapter}/content",
        headers={**w.headers, "If-Match": response.headers["etag"]},
        json={"content": "渡口烈日当空。"},
    )
    assert response.status_code == 200
    return chapter


def prepare(w, chapter=None):
    chapter = chapter or w.chapter
    response = w.client.post(
        f"/api/v1/chapters/{chapter}/memory/reviews",
        headers=w.headers,
        json={
            "source_revision": workspace(w, chapter)["source_revision"],
            "profile_id": "default-local",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def send(w, review, **extra):
    return w.client.post(
        f"/api/v1/chapters/{review['chapter_id']}/memory/reviews/{review['id']}/send",
        headers=w.headers,
        json={"expected_version": review["version"], **extra},
    )


def provider(w, *, facts=None, findings=None, raw=None):
    calls = []

    def invoke(*args):
        calls.append(args)
        text = (
            raw
            if raw is not None
            else json.dumps(
                {
                    "summary": "需核对天气承接",
                    "facts": facts or [],
                    "findings": findings or [],
                },
                ensure_ascii=False,
            )
        )
        return GeneratedText(text, "memory-test")

    w.app.state.story_memory_service._provider = invoke
    return calls


def test_pending_fact_never_recalled_confirmation_persists_and_freezes_source(workflow):
    w = workflow
    later = next_chapter(w)
    candidate = fact(w)
    assert workspace(w, later)["recalled_facts"] == []
    confirmed = confirm(w, candidate)
    assert confirmed["version"] == 2 and confirmed["revision_id"] != candidate["revision_id"]
    recalled = workspace(w, later)["recalled_facts"]
    assert [item["id"] for item in recalled] == [confirmed["id"]]
    assert workspace(w)["recalled_facts"] == []
    response = w.client.post(
        f"/api/v1/chapters/{later}/ai/runs",
        headers=w.headers,
        json={"profile_id": "default-local"},
    )
    assert response.status_code == 201
    run = response.json()
    assert "渡口正在下雨" in run["context"]["text"]
    source = next(
        item for item in run["context"]["manifest"]["sources"] if item["source"] == "story_memory"
    )
    assert source["references"] == [[confirmed["id"], confirmed["revision_id"]]]
    saved = w.client.get(w.base + "/content")
    w.client.put(
        w.base + "/content",
        headers={**w.headers, "If-Match": saved.headers["etag"]},
        json={"content": "雨已经停了。"},
    )
    state = workspace(w, later)
    assert state["facts"][0]["stale"] and state["recalled_facts"] == []
    assert {item["chapter_id"] for item in state["impacts"]} == {w.chapter, later}
    frozen = w.client.get(f"/api/v1/chapters/{later}/ai/runs/{run['run_id']}").json()
    assert frozen["context"] == run["context"]
    assert workspace(w)["source_revision"] != confirmed["source_revision"]
    updated = confirm(
        w,
        confirmed,
        source_revision=workspace(w)["source_revision"],
        quote="雨已经停了。",
        text="渡口雨停",
    )
    assert not workspace(w, later)["facts"][0]["stale"]
    assert workspace(w, later)["recalled_facts"][0]["revision_id"] == updated["revision_id"]


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "confirmed"},
        {"expected_version": 1},
        {"quote": "虚构引文"},
        {"title": ""},
        {"text": "坏\u0001数据"},
        {"source_revision": "missing"},
        {"status": "automatic"},
        {"unknown": "field"},
    ],
)
def test_fact_creation_rejects_unconfirmed_authority_invalid_source_or_fields(workflow, changes):
    w = workflow
    data = {
        "expected_version": 0,
        "source_revision": workspace(w)["source_revision"],
        "title": "事实",
        "text": "下雨",
        "quote": "雨😀雨。",
        **changes,
    }
    response = w.client.post(w.base + "/memory/facts", headers=w.headers, json=data)
    assert response.status_code in (409, 422)
    assert workspace(w)["facts"] == []


def test_stale_fact_update_conflict_and_sql_immutability(workflow):
    w = workflow
    current = fact(w)
    confirm(w, current)
    response = w.client.put(
        w.base + f"/memory/facts/{current['id']}",
        headers=w.headers,
        json={
            "expected_version": current["version"],
            "source_revision": current["source_revision"],
            "title": "旧修改",
            "text": "冲突",
            "quote": current["quote"],
            "status": "rejected",
        },
    )
    assert response.status_code == 409
    with closing(sqlite3.connect(w.db)) as connection:
        for operation in (
            "UPDATE story_memory_revisions SET version=99",
            "DELETE FROM story_memory_revisions",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(operation)
            connection.rollback()
        assert connection.execute("SELECT count(*) FROM story_memory_revisions").fetchone() == (2,)


def test_review_preparation_does_not_send_and_results_remain_candidates(workflow):
    w = workflow
    calls = provider(w, facts=[{"title": "天气", "text": "下雨", "quote": "雨😀雨。"}])
    before = w.client.get(w.base + "/content").json()
    review = prepare(w)
    assert review["content"] == "雨😀雨。" and calls == []
    response = send(w, review)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed" and result["attempts"] == 1
    assert len(calls) == 1
    assert json.loads(calls[0][1][1].content) == {"content": "雨😀雨。", "confirmed_facts": []}
    assert result["result"]["facts"][0]["text"] == "下雨"
    assert workspace(w)["facts"] == []
    assert w.client.get(w.base + "/content").json() == before
    assert send(w, result).status_code == 409


def test_cross_chapter_review_citations_and_impact_after_fact_rejection(workflow):
    w = workflow
    confirmed = confirm(w, fact(w))
    later = next_chapter(w)
    calls = provider(
        w,
        findings=[
            {
                "quote": "烈日当空",
                "explanation": "天气承接缺少过渡",
                "instruction": "交代雨停及时间变化",
                "fact_ids": [confirmed["id"]],
            }
        ],
    )
    review = prepare(w, later)
    assert review["facts"][0]["id"] == confirmed["id"]
    response = send(w, review)
    assert response.status_code == 200, response.text
    assert len(calls) == 1 and not workspace(w, later)["reviews"][0]["stale"]
    rejected = w.client.put(
        w.base + f"/memory/facts/{confirmed['id']}",
        headers=w.headers,
        json={
            **{key: confirmed[key] for key in ("title", "text", "quote", "source_revision")},
            "expected_version": confirmed["version"],
            "status": "rejected",
        },
    )
    assert rejected.status_code == 200
    state = workspace(w, later)
    assert state["reviews"][0]["stale"] and state["recalled_facts"] == []
    assert later in [item["chapter_id"] for item in state["impacts"]]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        '{"summary":"x","facts":[],"findings":[],"extra":1}',
        json.dumps(
            {
                "summary": "x",
                "facts": [{"title": "x", "text": "x", "quote": "编造"}],
                "findings": [],
            }
        ),
        json.dumps(
            {
                "summary": "x",
                "facts": [],
                "findings": [
                    {"quote": "雨", "explanation": "x", "instruction": "x", "fact_ids": ["missing"]}
                ],
            }
        ),
    ],
)
def test_model_invalid_output_is_saved_as_failed_without_retry(workflow, raw):
    w = workflow
    calls = provider(w, raw=raw)
    review = prepare(w)
    assert send(w, review).status_code == 422
    stored = workspace(w)["reviews"][0]
    assert stored["status"] == "failed" and stored["attempts"] == 1
    assert len(calls) == 1 and workspace(w)["facts"] == []


@pytest.mark.parametrize("failure", [AIProviderTimeout, RuntimeError])
def test_review_provider_failure_is_sanitized_and_attempts_are_bounded(workflow, failure):
    w = workflow
    calls = []

    def fail(*args):
        calls.append(args)
        raise failure("private upstream details")

    w.app.state.story_memory_service._provider = fail
    review = prepare(w)
    for attempt in range(3):
        response = send(w, review)
        assert response.status_code in (502, 504)
        assert "private" not in response.text
        review = workspace(w)["reviews"][0]
        assert review["attempts"] == attempt + 1 and review["status"] == "failed"
    assert send(w, review).status_code == 409 and len(calls) == 3


def test_cloud_consent_source_change_and_schema_boundary(workflow):
    w = workflow
    memory = w.app.state.story_memory_service
    memory._model_reader = lambda _: ModelSnapshot(
        "cloud", "云模型", "cloud", "https://example.invalid/v1", "model", 4000
    )
    calls = provider(w)
    review = prepare(w)
    assert send(w, review).status_code == 403 and calls == []
    content = w.client.get(w.base + "/content")
    w.client.put(
        w.base + "/content",
        headers={**w.headers, "If-Match": content.headers["etag"]},
        json={"content": "新的雨。"},
    )
    assert send(w, review, cloud_consent=True).status_code == 409 and calls == []
    w.app.state.ai_workflow_schema_required = True
    assert w.client.get(w.base + "/memory").status_code == 503
    w.app.state.ai_workflow_schema_required = False
    w.app.state.story_memory_service = None
    assert w.client.get(w.base + "/memory").status_code == 503


def test_review_only_one_concurrent_claim_can_call_provider(workflow):
    w = workflow
    entered, release = Event(), Event()
    memory = w.app.state.story_memory_service
    calls = provider(w)
    original = memory._provider

    def blocked(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    memory._provider = blocked
    review = prepare(w)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(memory.send, w.chapter, review["id"], 1, False)
        assert entered.wait(10)
        try:
            with pytest.raises(MemoryConflict):
                memory.send(w.chapter, review["id"], 1, False)
        finally:
            release.set()
        assert first.result().status == "completed"
    assert len(calls) == 1


def test_interrupted_review_recovers_once_without_model_send(workflow):
    w = workflow
    memory = w.app.state.story_memory_service
    calls = provider(w)
    review = Review.model_validate(prepare(w))
    running = review.model_copy(
        update={"revision_id": str(uuid4()), "version": 2, "status": "running", "attempts": 1}
    )
    memory._repository.save(running, 1, lambda: None)
    memory._repository.recover_interrupted()
    state = workspace(w)["reviews"][0]
    assert state["status"] == "failed" and state["version"] == 3 and calls == []
    memory._repository.recover_interrupted()
    assert workspace(w)["reviews"][0]["version"] == 3


def test_fact_and_review_cannot_be_accessed_through_another_chapter(workflow):
    w = workflow
    current = fact(w)
    later = next_chapter(w)
    review = prepare(w)
    response = w.client.put(
        f"/api/v1/chapters/{later}/memory/facts/{current['id']}",
        headers=w.headers,
        json={
            "expected_version": 1,
            "source_revision": current["source_revision"],
            "title": "x",
            "text": "x",
            "quote": "雨",
            "status": "confirmed",
        },
    )
    assert response.status_code == 404
    assert (
        w.client.post(
            f"/api/v1/chapters/{later}/memory/reviews/{review['id']}/send",
            headers=w.headers,
            json={"expected_version": 1},
        ).status_code
        == 404
    )
    assert w.client.post(w.base + "/memory/reviews", json={}).status_code in (401, 403)


def test_rejecting_stale_fact_preserves_original_evidence_without_reconfirming_it(workflow):
    w = workflow
    current = confirm(w, fact(w))
    content = w.client.get(w.base + "/content")
    w.client.put(
        w.base + "/content",
        headers={**w.headers, "If-Match": content.headers["etag"]},
        json={"content": "天气已晴。"},
    )
    data = {key: current[key] for key in ("title", "text", "quote", "source_revision")}
    data.update(expected_version=current["version"], status="rejected")
    response = w.client.put(w.base + f"/memory/facts/{current['id']}", headers=w.headers, json=data)
    assert response.status_code == 200, response.text
    assert response.json()["source_revision"] == current["source_revision"]
    assert workspace(w)["impacts"] == []
    assert workspace(w)["facts"][0]["status"] == "rejected"


def test_recall_budget_omissions_and_future_facts_are_explicit(workflow):
    w = workflow
    later = next_chapter(w)
    for index in range(26):
        confirm(w, fact(w, title=f"事实{index}", text="已发生且须保留的前文事实" * 50))
    state = workspace(w, later)
    assert state["omitted_facts"] > 0
    assert len(state["recalled_facts"]) <= 24
    assert len(json.dumps(state["recalled_facts"], ensure_ascii=False)) <= 10_000
    assert workspace(w)["recalled_facts"] == []
    review = prepare(w, later)
    assert review["omitted_facts"] == state["omitted_facts"]
    assert len(review["facts"]) == len(state["recalled_facts"])


def test_review_source_tail_bound_and_unchanged_provider_error_details(workflow):
    w = workflow
    content = w.client.get(w.base + "/content")
    saved = w.client.put(
        w.base + "/content",
        headers={**w.headers, "If-Match": content.headers["etag"]},
        json={"content": "前" * 25000 + "结尾。"},
    )
    assert saved.status_code == 200
    review = prepare(w)
    assert review["content_truncated"] and len(review["content"]) == 24_000
    assert review["content"].endswith("结尾。")


def test_deleted_project_memory_remains_hidden_and_recovery_does_not_rewrite_it(workflow):
    w = workflow
    current = fact(w)
    memory = w.app.state.story_memory_service
    review = Review.model_validate(prepare(w))
    running = review.model_copy(
        update={"revision_id": str(uuid4()), "version": 2, "status": "running", "attempts": 1}
    )
    memory._repository.save(running, 1, lambda: None)
    project = w.client.get(f"/api/v1/projects/{w.project}")
    deleted = w.client.post(
        f"/api/v1/projects/{w.project}/delete",
        headers={**w.headers, "If-Match": project.headers["etag"]},
    )
    assert deleted.status_code == 200
    with closing(sqlite3.connect(w.db)) as connection:
        count = connection.execute("SELECT count(*) FROM story_memory_revisions").fetchone()
    response = w.client.get(w.base + "/memory")
    assert response.status_code == 404
    memory._repository.recover_interrupted()
    with closing(sqlite3.connect(w.db)) as connection:
        assert connection.execute("SELECT count(*) FROM story_memory_revisions").fetchone() == count
        assert connection.execute(
            "SELECT entity_id FROM story_memory_revisions WHERE entity_id=?", (current["id"],)
        ).fetchone()


def test_memory_writer_checks_project_visibility_while_holding_sqlite_lock(workflow, monkeypatch):
    w = workflow
    current = MemoryFact.model_validate(fact(w))
    repository = w.app.state.story_memory_service._repository
    original = repository._projects.get_project
    checks = []

    def guarded(query):
        with (
            closing(sqlite3.connect(w.db, timeout=0)) as competing,
            pytest.raises(sqlite3.OperationalError, match="locked"),
        ):
            competing.execute("BEGIN IMMEDIATE")
        checks.append(query)
        return original(query)

    monkeypatch.setattr(repository._projects, "get_project", guarded)
    updated = current.model_copy(
        update={"revision_id": str(uuid4()), "version": 2, "status": "confirmed"}
    )
    assert repository.save(updated, 1, lambda: None).version == 2
    assert len(checks) == 1


def test_volume_reorder_invalidates_review_without_changing_fact_source_revision(workflow):
    w = workflow
    confirmed = confirm(w, fact(w))
    first_volume = w.client.get(w.base + "/content").json()["volume_id"]
    volume = w.client.post(
        f"/api/v1/projects/{w.project}/volumes",
        headers=w.headers,
        json={"title": "后卷", "summary": "", "position": 2},
    )
    assert volume.status_code == 201
    chapter = w.client.post(
        f"/api/v1/projects/{w.project}/volumes/{volume.json()['volume_id']}/chapters",
        headers=w.headers,
        json={"title": "后卷章", "summary": "", "position": 1},
    )
    assert chapter.status_code == 201
    target = chapter.json()["chapter_id"]
    saved = w.client.put(
        f"/api/v1/chapters/{target}/content",
        headers={**w.headers, "If-Match": chapter.headers["etag"]},
        json={"content": "渡口天气。"},
    )
    assert saved.status_code == 200
    review = prepare(w, target)
    assert review["facts"][0]["id"] == confirmed["id"]
    original = w.client.get(f"/api/v1/volumes/{first_volume}")
    changed = w.client.put(
        f"/api/v1/volumes/{first_volume}",
        headers={**w.headers, "If-Match": original.headers["etag"]},
        json={"title": "前卷后移", "summary": "", "position": 3},
    )
    assert changed.status_code == 200
    state = workspace(w, target)
    assert state["reviews"][0]["stale"] and state["recalled_facts"] == []
    assert not state["facts"][0]["stale"]
    assert send(w, review).status_code == 409
