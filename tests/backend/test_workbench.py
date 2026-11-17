"""Real migrated SQLite and HTTP prove derived workbench totals, to-dos and editorial state."""

import sqlite3
from contextlib import closing
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.backend.test_ai_workflow import TEXT, create_run, generate, workflow
from tests.backend.test_story_memory import confirm, fact, next_chapter, prepare

from aiwebnovel.core.errors import AppError
from aiwebnovel.story_memory.models import Review
from aiwebnovel.workbench.persistence import WHITESPACE_CODE_POINTS
from aiwebnovel.workbench.service import WorkbenchService, derive_actions
from aiwebnovel.workbench.snapshot import (
    ChapterRow,
    EditorialRow,
    FactReference,
    MemoryRow,
    ProjectSnapshot,
    VolumeRow,
)
from aiwebnovel.workbench.web import get_workbench_service

__all__ = ["workflow"]

SPACED = "\u3000第一句\t话。\n\n  第二 句\u00a0话\u2003!\u202f\u205f\u1680"


def non_whitespace(text):
    return sum(not character.isspace() for character in text)


def summary(w, project=None):
    response = w.client.get(f"/api/v1/projects/{project or w.project}/workspace")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def actions(w, **params):
    response = w.client.get(f"/api/v1/projects/{w.project}/workspace/actions", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def chapters(w, **params):
    response = w.client.get(f"/api/v1/projects/{w.project}/workspace/chapters", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def kinds(w):
    return {(item["kind"], item["chapter_id"]): item["count"] for item in actions(w)["items"]}


def save_content(w, chapter, content):
    current = w.client.get(f"/api/v1/chapters/{chapter}/content")
    response = w.client.put(
        f"/api/v1/chapters/{chapter}/content",
        headers={**w.headers, "If-Match": current.headers["etag"]},
        json={"content": content},
    )
    assert response.status_code == 200, response.text


def editorial(w, status, version, chapter=None):
    return w.client.put(
        f"/api/v1/chapters/{chapter or w.chapter}/editorial-state",
        headers=w.headers,
        json={"status": status, "expected_version": version},
    )


def add_volume(w, title, position):
    response = w.client.post(
        f"/api/v1/projects/{w.project}/volumes",
        headers=w.headers,
        json={"title": title, "summary": "", "position": position},
    )
    assert response.status_code == 201, response.text
    return response.json()["volume_id"]


def add_chapter(w, volume, title, position, content):
    response = w.client.post(
        f"/api/v1/projects/{w.project}/volumes/{volume}/chapters",
        headers=w.headers,
        json={"title": title, "summary": "", "position": position},
    )
    assert response.status_code == 201, response.text
    chapter = response.json()["chapter_id"]
    if content:
        save_content(w, chapter, content)
    return chapter


def test_whitespace_set_matches_python_isspace():
    assert tuple(code for code in range(0x110000) if chr(code).isspace()) == WHITESPACE_CODE_POINTS


def test_totals_are_server_side_non_whitespace_counts_per_novel_volume_and_chapter(workflow):
    w = workflow
    first_volume = w.client.get(w.base + "/content").json()["volume_id"]
    save_content(w, w.chapter, SPACED)
    second_volume = add_volume(w, "第二卷", 2)
    empty = add_chapter(w, second_volume, "空章", 1, "")
    later = add_chapter(w, second_volume, "后章", 2, "风  起。😀")
    result = summary(w)
    expected_first = non_whitespace(SPACED)
    assert expected_first == 10
    assert result["characters"] == expected_first + non_whitespace("风  起。😀")
    assert result["chapter_count"] == 3
    assert result["volume_count"] == 2
    assert result["editorial"] == {"draft": 3, "review": 0, "final": 0}
    assert [(v["volume_id"], v["chapter_count"], v["characters"]) for v in result["volumes"]] == [
        (first_volume, 1, expected_first),
        (second_volume, 2, 4),
    ]
    assert result["latest_chapter"]["chapter_id"] == later
    assert result["action_total"] == 0
    assert {item["kind"] for item in result["actions"]} == {
        "due_thread",
        "budget_reminder",
        "stale_fact",
        "stale_review",
        "final_changed",
        "pending_candidate",
        "pending_fact",
        "unfinished_review",
    }
    page = chapters(w)
    assert [item["chapter_id"] for item in page["items"]] == [w.chapter, empty, later]
    assert [item["characters"] for item in page["items"]] == [expected_first, 0, 4]
    assert page["total"] == 3 and page["next_offset"] is None
    assert w.calls == []


def test_ai_candidates_never_count_as_manuscript_and_appear_once_as_todo(workflow):
    w = workflow
    before = summary(w)["characters"]
    run = generate(w, create_run(w, max_steps=2, max_output_characters=600))
    assert len(run["candidates"]) == 1
    result = summary(w)
    assert result["characters"] == before == non_whitespace("雨😀雨。")
    assert result["action_total"] == 1
    assert kinds(w) == {("pending_candidate", w.chapter): 1}
    assert TEXT not in str(result)
    candidate = run["candidates"][0]
    w.service.adopt(w.chapter, candidate["candidate_id"], 2, "adopt-once")
    after = summary(w)
    assert after["characters"] == non_whitespace("雨😀雨。" + TEXT)
    assert after["action_total"] == 0
    assert len(w.calls) == 1  # Only the explicit generate call reached the provider.


def test_pagination_volume_filter_and_strict_query_validation(workflow):
    w = workflow
    volume = w.client.get(w.base + "/content").json()["volume_id"]
    created = [add_chapter(w, volume, f"第{n}章", n, "字" * n) for n in range(2, 6)]
    first = chapters(w, limit=2)
    assert [item["chapter_id"] for item in first["items"]] == [w.chapter, created[0]]
    assert (first["total"], first["offset"], first["limit"], first["next_offset"]) == (5, 0, 2, 2)
    last = chapters(w, offset=4, limit=2, volume_id=volume)
    assert [item["chapter_id"] for item in last["items"]] == [created[-1]]
    assert last["next_offset"] is None and last["volume_id"] == volume
    assert chapters(w, offset=9)["items"] == []
    base = f"/api/v1/projects/{w.project}/workspace"
    for url in (
        base + "/chapters?limit=0",
        base + "/chapters?limit=101",
        base + "/chapters?limit=-1",
        base + "/chapters?limit=1&limit=2",
        base + "/chapters?offset=abc",
        base + "/chapters?offset=99999999",
        base + "/chapters?cursor=x",
        base + "/chapters?volume_id=a&volume_id=b",
        base + "/actions?volume_id=x",
        base + "/actions?limit=",
    ):
        response = w.client.get(url)
        assert response.status_code == 422, url
        assert response.json()["error"]["code"] == "INVALID_WORKBENCH_QUERY"
    missing = w.client.get(base + "/chapters?volume_id=vol_01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "VOLUME_NOT_FOUND"
    assert actions(w, limit=1) == {
        "project_id": w.project,
        "total": 0,
        "offset": 0,
        "limit": 1,
        "next_offset": None,
        "items": [],
    }


def test_editorial_state_is_author_chosen_versioned_immutable_and_tracks_later_edits(workflow):
    w = workflow
    url = w.base + "/editorial-state"
    initial = w.client.get(url)
    assert initial.status_code == 200
    assert initial.headers["cache-control"] == "no-store"
    assert initial.json() == {
        "chapter_id": w.chapter,
        "project_id": w.project,
        "status": "draft",
        "version": 0,
        "chapter_revision_id": None,
        "content_changed": False,
        "open_actions": 0,
        "updated_at": None,
    }
    review = editorial(w, "review", 0)
    assert review.status_code == 200, review.text
    assert review.json()["version"] == 1 and review.json()["status"] == "review"
    stale = editorial(w, "final", 0)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "EDITORIAL_CONFLICT"
    final = editorial(w, "final", 1).json()
    assert final["version"] == 2 and final["content_changed"] is False
    assert w.client.get(url).json() == final
    content = w.client.get(w.base + "/content").json()
    assert final["chapter_revision_id"] == content["current_revision_id"]
    assert summary(w)["editorial"] == {"draft": 0, "review": 0, "final": 1}
    assert summary(w)["action_total"] == 0
    save_content(w, w.chapter, "雨😀雨。改。")
    changed = w.client.get(url).json()
    assert changed["status"] == "final" and changed["content_changed"] is True
    assert kinds(w) == {("final_changed", w.chapter): 1}
    assert changed["open_actions"] == 0  # The changed-after-final note is shown separately.
    row = chapters(w)["items"][0]
    assert row["editorial_status"] == "final" and row["editorial_version"] == 2
    assert row["content_changed_since_editorial"] is True and row["open_actions"] == 1
    # Marking final again acknowledges the current text and clears the derived to-do.
    assert editorial(w, "final", 2).json()["content_changed"] is False
    assert kinds(w) == {}
    with closing(sqlite3.connect(w.db)) as connection:
        assert connection.execute(
            "SELECT version, status FROM chapter_editorial_revisions ORDER BY version"
        ).fetchall() == [(1, "review"), (2, "final"), (3, "final")]
        for operation in (
            "UPDATE chapter_editorial_revisions SET status='draft'",
            "DELETE FROM chapter_editorial_revisions",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(operation)
    assert w.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "done", "expected_version": 0},
        {"status": "final", "expected_version": -1},
        {"status": "final"},
        {"status": "final", "expected_version": 0, "extra": 1},
        {"status": "final", "expected_version": "0"},
    ],
)
def test_editorial_state_rejects_invalid_payloads(workflow, payload):
    w = workflow
    response = w.client.put(w.base + "/editorial-state", headers=w.headers, json=payload)
    assert response.status_code == 422
    assert w.client.get(w.base + "/editorial-state").json()["version"] == 0


def test_editorial_state_requires_json_csrf_and_valid_visible_chapter(workflow):
    w = workflow
    url = w.base + "/editorial-state"
    body = {"status": "final", "expected_version": 0}
    assert w.client.put(url, json=body).status_code in (401, 403)
    as_text = w.client.put(
        url,
        headers={**w.headers, "Content-Type": "text/plain"},
        content=b'{"status":"final","expected_version":0}',
    )
    assert as_text.status_code == 415
    invalid = w.client.get("/api/v1/chapters/not-an-id/editorial-state")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_CHAPTER_ID"
    missing = w.client.get("/api/v1/chapters/chp_01ARZ3NDEKTSV4RRFFQ69G5FAV/editorial-state")
    assert missing.status_code == 404
    assert w.client.get(url).json()["version"] == 0


def test_memory_todos_are_deduplicated_and_follow_source_changes(workflow):
    w = workflow
    pending = fact(w)
    rejected = fact(w, title="被驳回")
    rejected_data = {key: rejected[key] for key in ("title", "text", "quote", "source_revision")}
    response = w.client.put(
        w.base + f"/memory/facts/{rejected['id']}",
        headers=w.headers,
        json={**rejected_data, "expected_version": 1, "status": "rejected"},
    )
    assert response.status_code == 200, response.text
    review = prepare(w)
    assert review["status"] == "ready"
    assert w.client.get(w.base + "/editorial-state").json()["open_actions"] == 2
    assert kinds(w) == {("pending_fact", w.chapter): 1, ("unfinished_review", w.chapter): 1}
    result = summary(w)
    assert result["action_total"] == 2
    assert {item["kind"]: item["items"] for item in result["actions"]}["pending_fact"] == 1
    confirm(w, pending)
    assert kinds(w) == {("unfinished_review", w.chapter): 1}
    save_content(w, w.chapter, "雨😀雨。新增一句。")
    # The confirmed fact and the prepared review now cite an old source revision.
    assert kinds(w) == {("stale_fact", w.chapter): 1, ("stale_review", w.chapter): 1}
    ordered = actions(w)["items"]
    assert [item["kind"] for item in ordered] == ["stale_fact", "stale_review"]
    assert ordered[0]["chapter_title"] == "测试章" and ordered[0]["count"] == 1
    page = actions(w, limit=1)
    assert page["total"] == 2 and page["next_offset"] == 1
    assert actions(w, offset=1, limit=1)["items"][0]["kind"] == "stale_review"
    assert w.calls == []


def test_later_chapter_review_is_stale_when_cited_fact_changes(workflow):
    w = workflow
    confirmed = confirm(w, fact(w))
    later = next_chapter(w)
    memory = w.app.state.story_memory_service
    review = Review.model_validate(prepare(w, later))
    assert [item.id for item in review.facts] == [confirmed["id"]]
    completed = review.model_copy(
        update={"revision_id": str(uuid4()), "version": 2, "status": "completed", "attempts": 1}
    )
    memory._repository.save(completed, 1, lambda: None)
    assert kinds(w) == {}
    save_content(w, w.chapter, "雨😀雨。改写。")
    assert kinds(w) == {("stale_fact", w.chapter): 1, ("stale_review", later): 1}
    assert w.calls == []


def test_deleted_or_invalid_project_is_hidden(workflow):
    w = workflow
    editorial(w, "final", 0)
    project = w.client.get(f"/api/v1/projects/{w.project}")
    deleted = w.client.post(
        f"/api/v1/projects/{w.project}/delete",
        headers={**w.headers, "If-Match": project.headers["etag"]},
    )
    assert deleted.status_code == 200
    for suffix in ("", "/chapters", "/actions"):
        response = w.client.get(f"/api/v1/projects/{w.project}/workspace{suffix}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert w.client.get(w.base + "/editorial-state").status_code == 404
    assert editorial(w, "draft", 1).status_code == 404
    invalid = w.client.get("/api/v1/projects/bad-id/workspace")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_PROJECT_ID"


def test_service_dependency_reports_schema_and_availability():
    def request(**state):
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))

    with pytest.raises(AppError) as schema:
        get_workbench_service(request(ai_workflow_schema_required=True))
    assert schema.value.code == "AI_WORKFLOW_SCHEMA_REQUIRED"
    assert schema.value.status_code == 503
    with pytest.raises(AppError) as missing:
        get_workbench_service(request(workbench_service=None))
    assert missing.value.code == "WORKBENCH_UNAVAILABLE"
    service = WorkbenchService(SimpleNamespace())
    assert get_workbench_service(request(workbench_service=service)) is service


def _chapter(identifier, position, revision):
    return ChapterRow(identifier, "v", 1, position, identifier, revision, "2026-10-01", 5)


def _review(entity, chapter, status, source, facts=(), updated="2026-10-02"):
    return MemoryRow(entity, chapter, "review", status, source, entity + "r", updated, facts)


def _fact(entity, chapter, status, source, revision="f1"):
    return MemoryRow(entity, chapter, "fact", status, source, revision, "2026-10-01", ())


def test_derived_review_states_use_only_the_latest_review_per_chapter():
    snapshot = ProjectSnapshot(
        volumes=(VolumeRow("v", "卷", 1),),
        chapters=(_chapter("a", 1, "ra"), _chapter("b", 2, "rb"), _chapter("c", 3, "rc")),
        editorial={
            "a": EditorialRow("final", 1, "ra", "t"),
            "b": EditorialRow("review", 1, "old", "t"),
            "gone": EditorialRow("final", 1, "x", "t"),
        },
        pending_candidates={"c": 2, "gone": 1},
        memory=(
            _fact("f", "a", "confirmed", "ra"),
            _fact("g", "a", "pending", "old"),
            _review("old", "a", "failed", "ra", updated="2026-10-01"),
            _review("new", "a", "completed", "ra", updated="2026-10-03"),
            _review("running", "b", "running", "old"),
            _review("failed", "c", "failed", "rc", (FactReference("f", "f1", "a"),)),
            _review(
                "missing", "b", "completed", "rb", (FactReference("x", "x1", "a"),), "2026-09-01"
            ),
        ),
    )
    items = derive_actions(snapshot)
    assert [(item.kind, item.chapter_id, item.count) for item in items] == [
        ("stale_fact", "a", 1),
        ("pending_candidate", "c", 2),
        ("unfinished_review", "c", 1),
    ]
    # A cited fact from a later or same chapter, or at a new revision, makes a review stale.
    future = ProjectSnapshot(
        volumes=snapshot.volumes,
        chapters=snapshot.chapters,
        editorial={},
        pending_candidates={},
        memory=(
            _fact("f", "c", "confirmed", "rc"),
            _fact("h", "a", "confirmed", "ra", revision="h2"),
            _review("r1", "b", "ready", "rb", (FactReference("f", "f1", "c"),)),
            _review("r2", "c", "completed", "rc", (FactReference("h", "h1", "a"),)),
        ),
    )
    assert [(item.kind, item.chapter_id) for item in derive_actions(future)] == [
        ("stale_review", "b"),
        ("stale_review", "c"),
    ]


def test_summary_of_empty_project_has_no_invented_numbers():
    snapshot = ProjectSnapshot((), (), {}, {}, ())
    repository = SimpleNamespace(snapshot=lambda _project: snapshot)
    result = WorkbenchService(repository, clock=lambda: "now").summary("p")
    assert result.characters == 0 and result.chapter_count == 0 and result.volume_count == 0
    assert result.latest_chapter is None and result.volumes == [] and result.action_total == 0
    assert all(item.items == 0 and item.chapters == 0 for item in result.actions)
    assert result.generated_at == "now"
