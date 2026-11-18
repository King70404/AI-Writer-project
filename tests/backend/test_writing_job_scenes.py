"""Author-recorded scene progress in writing plans; no model request is ever made by it."""

import sqlite3
from contextlib import closing

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_chapter_planning import document

__all__ = ["workflow"]


def _scene(identifier, title):
    return {
        "id": identifier,
        "title": title,
        "setting": "渡口",
        "character_ids": [],
        "beats": [{"id": f"{identifier}-b", "action": "推进", "change": "变化"}],
    }


def _plan(w, expected_version, scenes):
    response = w.client.put(
        w.base + "/planning",
        headers=w.headers,
        json=document(expected_version=expected_version, scenes=scenes),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _job(w):
    response = w.client.post(
        f"/api/v1/projects/{w.project}/writing-jobs",
        headers=w.headers,
        json={"title": "场景任务", "chapter_ids": [w.chapter]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mark(w, job, version, revision, action, scene=None, step=0):
    body = {
        "expected_version": version,
        "step_index": step,
        "plan_revision_id": revision,
        "action": action,
    }
    if scene is not None:
        body["scene_id"] = scene
    return w.client.post(
        f"/api/v1/writing-jobs/{job['job_id']}/scene-progress", headers=w.headers, json=body
    )


def _marks(w):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute("SELECT COUNT(*) FROM writing_job_scene_marks").fetchone()[0]


def test_scene_marks_follow_author_adoption_and_version_checks(workflow):
    from tests.backend.test_ai_workflow import create_run, generate

    w = workflow
    plan = _plan(w, 0, [_scene("quay", "渡口盘问"), _scene("deck", "甲板夜谈")])
    job = _job(w)
    progress = job["scene_progress"][0]
    assert progress["plan_revision_id"] == plan["revision_id"]
    assert progress["plan_version"] == 1 and progress["needs_recheck"] is False
    assert progress["total"] == 2 and progress["next_scene_id"] == "quay"
    assert [s["status"] for s in progress["scenes"]] == ["pending", "pending"]
    revision = plan["revision_id"]

    targeted = _mark(w, job, 1, revision, "target", "quay")
    assert targeted.status_code == 200, targeted.text
    assert targeted.json()["version"] == 2
    assert targeted.json()["scene_progress"][0]["target_scene_id"] == "quay"
    # A stale page cannot overwrite a newer author decision.
    stale = _mark(w, job, 1, revision, "skipped", "deck")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "WRITING_JOB_CONFLICT"
    assert _marks(w) == 1
    # Re-targeting the same scene is not a new decision.
    assert _mark(w, job, 2, revision, "target", "quay").status_code == 409
    # "Done" needs an adopted candidate in this chapter step.
    assert _mark(w, job, 2, revision, "done", "quay").status_code == 409
    assert _mark(w, job, 2, revision, "target", "missing").status_code == 422
    assert _mark(w, job, 2, revision, "target", "deck", step=1).status_code == 409
    assert _mark(w, job, 2, revision, "recheck").status_code == 409
    skipped = _mark(w, job, 2, revision, "skipped", "deck")
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["scene_progress"][0]["skipped_count"] == 1
    assert not w.calls

    run = create_run(w)
    bound = w.client.post(
        f"/api/v1/writing-jobs/{job['job_id']}/bind-run",
        headers=w.headers,
        json={"expected_version": 3, "run_id": run["run_id"]},
    )
    assert bound.status_code == 200, bound.text
    candidate = generate(w, run)["candidates"][0]
    assert len(w.calls) == 1
    # Generation alone never marks a scene done.
    after_generate = w.client.get(f"/api/v1/writing-jobs/{job['job_id']}").json()
    assert after_generate["scene_progress"][0]["done_count"] == 0
    assert after_generate["scene_progress"][0]["has_adopted"] is False
    assert _mark(w, job, 4, revision, "done", "quay").status_code == 409
    w.service.adopt(w.chapter, candidate["candidate_id"], 2, "scene-adopt-key")
    after_adopt = w.client.get(f"/api/v1/writing-jobs/{job['job_id']}").json()
    assert after_adopt["scene_progress"][0]["done_count"] == 0
    assert after_adopt["scene_progress"][0]["has_adopted"] is True
    done = _mark(w, job, 4, revision, "done", "quay")
    assert done.status_code == 200, done.text
    progress = done.json()["scene_progress"][0]
    assert progress["done_count"] == 1 and progress["skipped_count"] == 1
    assert progress["target_scene_id"] is None and progress["next_scene_id"] is None
    reopened = _mark(w, job, 5, revision, "pending", "deck")
    assert reopened.status_code == 200
    assert reopened.json()["scene_progress"][0]["next_scene_id"] == "deck"
    assert _mark(w, job, 6, revision, "pending", "deck").status_code == 409
    assert len(w.calls) == 1

    with closing(sqlite3.connect(w.db)) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE writing_job_scene_marks SET action='done'")


def test_plan_change_requires_explicit_recheck_without_remapping(workflow):
    w = workflow
    first = _plan(w, 0, [_scene("quay", "渡口盘问"), _scene("deck", "甲板夜谈")])
    job = _job(w)
    assert _mark(w, job, 1, first["revision_id"], "skipped", "quay").status_code == 200
    second = _plan(w, 1, [_scene("deck", "甲板夜谈改稿"), _scene("hold", "货舱")])

    reread = w.client.get(f"/api/v1/writing-jobs/{job['job_id']}").json()
    progress = reread["scene_progress"][0]
    assert progress["needs_recheck"] is True
    assert progress["plan_revision_id"] == first["revision_id"] and progress["plan_version"] == 1
    assert progress["current_plan_revision_id"] == second["revision_id"]
    assert progress["current_plan_version"] == 2
    # Old marks stay attached to the old scene list.
    assert [(s["scene_id"], s["title"], s["status"]) for s in progress["scenes"]] == [
        ("quay", "渡口盘问", "skipped"),
        ("deck", "甲板夜谈", "pending"),
    ]
    old = _mark(w, job, 2, first["revision_id"], "target", "deck")
    assert old.status_code == 409
    assert old.json()["error"]["code"] == "WRITING_JOB_SCENE_PLAN_CHANGED"
    blocked = _mark(w, job, 2, second["revision_id"], "target", "deck")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "WRITING_JOB_SCENE_RECHECK_REQUIRED"
    assert _mark(w, job, 2, second["revision_id"], "recheck", "deck").status_code == 409

    rechecked = _mark(w, job, 2, second["revision_id"], "recheck")
    assert rechecked.status_code == 200, rechecked.text
    progress = rechecked.json()["scene_progress"][0]
    assert progress["needs_recheck"] is False and progress["plan_version"] == 2
    assert [(s["scene_id"], s["status"]) for s in progress["scenes"]] == [
        ("deck", "pending"),
        ("hold", "pending"),
    ]
    assert progress["next_scene_id"] == "deck"
    assert _mark(w, job, 3, second["revision_id"], "recheck").status_code == 409
    assert _mark(w, job, 3, second["revision_id"], "target", "hold").status_code == 200
    assert _marks(w) == 3
    assert not w.calls


def test_scene_marks_respect_job_state_and_missing_plan(workflow):
    w = workflow
    job = _job(w)
    progress = job["scene_progress"][0]
    assert progress["total"] == 0 and progress["plan_revision_id"] is None
    assert progress["needs_recheck"] is False and progress["next_scene_id"] is None
    assert _mark(w, job, 1, "missing-plan", "target", "quay").status_code == 409
    plan = _plan(w, 0, [_scene("quay", "渡口盘问")])
    path = f"/api/v1/writing-jobs/{job['job_id']}"
    assert (
        w.client.post(path + "/pause", headers=w.headers, json={"expected_version": 1}).status_code
        == 200
    )
    # The author may still record decisions while new sending is paused.
    assert _mark(w, job, 2, plan["revision_id"], "skipped", "quay").status_code == 200
    assert (
        w.client.post(path + "/cancel", headers=w.headers, json={"expected_version": 3}).status_code
        == 200
    )
    assert _mark(w, job, 4, plan["revision_id"], "pending", "quay").status_code == 409
    missing = "/api/v1/writing-jobs/00000000-0000-0000-0000-000000000000/scene-progress"
    response = w.client.post(
        missing,
        headers=w.headers,
        json={
            "expected_version": 1,
            "step_index": 0,
            "plan_revision_id": plan["revision_id"],
            "action": "recheck",
        },
    )
    assert response.status_code == 404
    unknown = _mark(w, job, 4, plan["revision_id"], "adopt", "quay")
    assert unknown.status_code == 422
    assert not w.calls
