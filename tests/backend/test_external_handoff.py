"""External handoff must not write until explicit adoption."""

from uuid import uuid4

from tests.backend.test_ai_workflow import workflow

__all__ = ["workflow"]


def test_handoff_roundtrip(workflow):
    w = workflow
    root = w.base + "/handoffs"
    request = {"instruction": "续写", "include_manuscript": True}
    preview = w.client.post(root + "/preview", headers=w.headers, json=request)
    assert preview.status_code == 200, preview.text
    task = w.client.post(
        root,
        headers=w.headers,
        json={**request, "context_sha256": preview.json()["context_sha256"]},
    )
    assert task.status_code == 200, task.text
    task = task.json()
    payload = {
        "format_version": 1,
        "handoff_id": task["handoff_id"],
        "context_sha256": task["context_sha256"],
        "text": "旅人走过古桥。" * 30,
    }
    path = root + "/" + task["handoff_id"] + "/candidates"
    result = w.client.post(path, headers=w.headers, json=payload)
    assert result.status_code == 200, result.text
    assert w.client.post(path, headers=w.headers, json=payload).json() == result.json()
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"
    key = str(uuid4())
    response = w.client.post(
        path + "/" + result.json()["candidate_id"] + "/adopt",
        headers={**w.headers, "If-Match": '"2"'},
        json={"idempotency_key": key},
    )
    assert response.status_code == 200, response.text
    assert w.client.get(w.base + "/content").json()["content"].endswith(payload["text"])
    assert not w.calls


def test_external_handoff_rejects_forged_or_stale_input(workflow):
    w = workflow
    root = w.base + "/handoffs"
    request = {"instruction": "续写", "include_manuscript": False}
    preview = w.client.post(root + "/preview", headers=w.headers, json=request).json()
    assert (
        w.client.post(
            root, headers=w.headers, json={**request, "context_sha256": "0" * 64}
        ).status_code
        == 409
    )
    task = w.client.post(
        root, headers=w.headers, json={**request, "context_sha256": preview["context_sha256"]}
    ).json()
    path = root + "/" + task["handoff_id"] + "/candidates"
    assert (
        w.client.post(
            path,
            headers={**w.headers, "content-type": "application/json"},
            content=b'{"text":"a","text":"b"}',
        ).status_code
        == 422
    )
    value = "山雨落在渡船上。" * 30
    payload = {
        "format_version": 1,
        "handoff_id": task["handoff_id"],
        "context_sha256": task["context_sha256"],
        "text": value,
    }
    imported = w.client.post(path, headers=w.headers, json=payload)
    assert imported.status_code == 200, imported.text
    cid = imported.json()["candidate_id"]
    assert w.client.post(path, headers=w.headers, json=payload).json()["candidate_id"] == cid
    changed = w.client.put(
        w.base + "/content",
        headers={**w.headers, "If-Match": '"2"'},
        json={"content": "作者新正文"},
    )
    assert changed.status_code == 200
    response = w.client.post(
        path + "/" + cid + "/adopt",
        headers={**w.headers, "If-Match": '"2"'},
        json={"idempotency_key": str(uuid4())},
    )
    assert response.status_code == 409
    assert w.client.get(w.base + "/content").json()["content"] == "作者新正文"


def test_only_selected_current_sources_are_exported(workflow):
    import json
    import sqlite3
    from contextlib import closing

    w = workflow
    revision = w.client.get(w.base + "/content").json()["current_revision_id"]
    rule_id, fact_id, entity_id, plan_id = (str(uuid4()) for _ in range(4))
    with closing(sqlite3.connect(w.db)) as db, db:
        db.execute(
            "INSERT INTO chapter_plan_revisions (id,chapter_id,project_id,version,payload,created_at) VALUES (?,?,?,?,?,?)",
            (
                plan_id,
                w.chapter,
                w.project,
                1,
                json.dumps({"chapter_goal": "本章目标"}),
                "2026-01-01",
            ),
        )
        db.execute(
            "INSERT INTO writing_rule_versions (id,rule_id,project_id,version,reference_id,payload) VALUES (?,?,?,?,?,?)",
            (rule_id, str(uuid4()), w.project, 1, None, json.dumps({"title": "规则"})),
        )
        db.execute(
            "INSERT INTO story_memory_revisions (id,entity_id,project_id,chapter_id,version,payload) VALUES (?,?,?,?,?,?)",
            (
                fact_id,
                entity_id,
                w.project,
                w.chapter,
                1,
                json.dumps(
                    {
                        "kind": "fact",
                        "status": "confirmed",
                        "title": "事实",
                        "text": "旅人",
                        "quote": "雨",
                        "source_revision": revision,
                    }
                ),
            ),
        )
    root = w.base + "/handoffs"
    request = {
        "instruction": "任务",
        "include_manuscript": False,
        "include_plan": True,
        "rule_revision_ids": [rule_id],
        "fact_revision_ids": [fact_id],
    }
    preview = w.client.post(root + "/preview", headers=w.headers, json=request)
    assert preview.status_code == 200, preview.text
    context = json.loads(preview.json()["context"])
    assert [item["kind"] for item in context["sources"]] == ["plan", "rule", "fact"]
    assert context["manuscript"] == ""
    task = w.client.post(
        root,
        headers=w.headers,
        json={**request, "context_sha256": preview.json()["context_sha256"]},
    )
    assert task.status_code == 200, task.text
    path = root + "/" + task.json()["handoff_id"] + "/candidates"
    payload = {
        "format_version": 1,
        "handoff_id": task.json()["handoff_id"],
        "context_sha256": preview.json()["context_sha256"],
        "text": "风吹过江面。" * 40,
    }
    candidate = w.client.post(path, headers=w.headers, json=payload).json()
    with closing(sqlite3.connect(w.db)) as db, db:
        db.execute(
            "INSERT INTO chapter_plan_revisions (id,chapter_id,project_id,version,payload,created_at) VALUES (?,?,?,?,?,?)",
            (
                str(uuid4()),
                w.chapter,
                w.project,
                2,
                json.dumps({"chapter_goal": "变更"}),
                "2026-01-01",
            ),
        )
    result = w.client.post(
        path + "/" + candidate["candidate_id"] + "/adopt",
        headers={**w.headers, "If-Match": '"2"'},
        json={"idempotency_key": str(uuid4())},
    )
    assert result.status_code == 409
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"
