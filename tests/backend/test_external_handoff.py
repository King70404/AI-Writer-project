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


def _task(w, request=None):
    root = w.base + "/handoffs"
    request = request or {"instruction": "续写", "include_manuscript": False}
    preview = w.client.post(root + "/preview", headers=w.headers, json=request).json()
    task = w.client.post(
        root, headers=w.headers, json={**request, "context_sha256": preview["context_sha256"]}
    ).json()
    return root, task


def test_listing_and_download_contain_only_the_frozen_snapshot(workflow):
    import io
    import json
    import zipfile

    w = workflow
    root, task = _task(w, {"instruction": "续写", "include_manuscript": False})
    listing = w.client.get(root, headers=w.headers)
    assert listing.status_code == 200, listing.text
    assert [item["handoff_id"] for item in listing.json()] == [task["handoff_id"]]
    assert listing.json()[0]["candidates"] == []
    before = w.client.get(root, headers=w.headers).json()
    download = w.client.get(root + "/" + task["handoff_id"] + "/download", headers=w.headers)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert download.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert sorted(archive.namelist()) == ["context.json", "manifest.json", "task.md"]
        context = json.loads(archive.read("context.json"))
        manifest = json.loads(archive.read("manifest.json"))
        blob = b"".join(archive.read(name) for name in archive.namelist())
    assert context["manuscript"] == ""
    assert "雨😀雨".encode() not in blob
    assert b"api_key" not in blob.lower() and b"sk-" not in blob
    assert manifest == {
        "format_version": 1,
        "handoff_id": task["handoff_id"],
        "context_sha256": task["context_sha256"],
    }
    assert w.client.get(root, headers=w.headers).json() == before
    missing = w.client.get(root + "/" + str(uuid4()) + "/download", headers=w.headers)
    assert missing.status_code == 404
    assert not w.calls


def test_candidate_import_rejects_invalid_payloads(workflow):
    import json

    w = workflow
    root, task = _task(w)
    path = root + "/" + task["handoff_id"] + "/candidates"
    good = "旅人走过古桥。" * 30
    base = {
        "format_version": 1,
        "handoff_id": task["handoff_id"],
        "context_sha256": task["context_sha256"],
        "text": good,
    }
    json_headers = {**w.headers, "content-type": "application/json"}
    cases = [
        (json_headers, json.dumps({**base, "extra": 1}).encode(), 422),
        (json_headers, json.dumps({**base, "format_version": 2}).encode(), 422),
        (json_headers, json.dumps({**base, "format_version": True}).encode(), 422),
        (json_headers, json.dumps({**base, "handoff_id": str(uuid4())}).encode(), 422),
        (json_headers, json.dumps({**base, "context_sha256": "0" * 64}).encode(), 422),
        (json_headers, json.dumps({**base, "text": 1}).encode(), 422),
        (json_headers, json.dumps({**base, "text": ""}).encode(), 422),
        (json_headers, json.dumps({**base, "text": "短"}).encode(), 422),
        (json_headers, json.dumps({**base, "text": "长" * 301}).encode(), 422),
        (json_headers, json.dumps([base]).encode(), 422),
        (json_headers, b"\xff\xfe", 422),
        (json_headers, b"{" + b" " * 262144, 413),
        ({**w.headers, "content-type": "text/csv"}, good.encode(), 415),
        ({**w.headers, "content-type": "text/plain"}, good.encode(), 415),
    ]
    for headers, body, status in cases:
        response = w.client.post(path, headers=headers, content=body)
        assert response.status_code == status, (body[:40], response.text)
    control = w.client.post(path, headers=w.headers, json={**base, "text": "旅\x00" * 150})
    assert control.status_code == 422
    chapters = w.base.rsplit("/", 1)[0]
    malformed = w.client.post(
        chapters + "/not-a-chapter/handoffs/" + task["handoff_id"] + "/candidates",
        headers=json_headers,
        content=json.dumps(base).encode(),
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "INVALID_CHAPTER_ID"
    unknown_chapter = "chp_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    for response in (
        w.client.get(chapters + "/" + unknown_chapter + "/handoffs", headers=w.headers),
        w.client.post(
            chapters + "/" + unknown_chapter + "/handoffs/preview",
            headers=w.headers,
            json={"instruction": "x", "include_manuscript": False},
        ),
    ):
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"
    assert not w.calls


def test_adoption_is_idempotent_and_rejects_forged_keys(workflow):
    w = workflow
    root, task = _task(w)
    path = root + "/" + task["handoff_id"] + "/candidates"
    text = "山雨落在渡船上。" * 30
    created = w.client.post(
        path,
        headers=w.headers,
        json={
            "format_version": 1,
            "handoff_id": task["handoff_id"],
            "context_sha256": task["context_sha256"],
            "text": text,
        },
    ).json()
    adopt = path + "/" + created["candidate_id"] + "/adopt"
    headers = {**w.headers, "If-Match": '"2"'}
    assert w.client.post(adopt, headers=headers, json={"idempotency_key": "x"}).status_code == 422
    assert (
        w.client.post(
            path + "/" + str(uuid4()) + "/adopt",
            headers=headers,
            json={"idempotency_key": str(uuid4())},
        ).status_code
        == 404
    )
    key = str(uuid4())
    first = w.client.post(adopt, headers=headers, json={"idempotency_key": key})
    assert first.status_code == 200, first.text
    content = w.client.get(w.base + "/content").json()["content"]
    again = w.client.post(adopt, headers=headers, json={"idempotency_key": key})
    assert again.status_code == 200 and again.json()["status"] == "adopted"
    other = w.client.post(adopt, headers=headers, json={"idempotency_key": str(uuid4())})
    assert other.status_code == 409
    assert w.client.get(w.base + "/content").json()["content"] == content
    assert content.count(text) == 1
    listing = w.client.get(root, headers=w.headers).json()
    assert listing[0]["candidates"][0]["status"] == "adopted"


def test_preview_rejects_duplicate_missing_or_foreign_sources(workflow):
    import json
    import sqlite3
    from contextlib import closing

    w = workflow
    root = w.base + "/handoffs"
    rule, fact, proposed = (str(uuid4()) for _ in range(3))
    revision = w.client.get(w.base + "/content").json()["current_revision_id"]
    with closing(sqlite3.connect(w.db)) as db, db:
        db.execute(
            "INSERT INTO writing_rule_versions (id,rule_id,project_id,version,reference_id,payload) VALUES (?,?,?,?,?,?)",
            (
                rule,
                str(uuid4()),
                "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV",
                1,
                None,
                json.dumps({"title": "他书"}),
            ),
        )
        for rid, status, source in ((fact, "confirmed", "stale"), (proposed, "proposed", revision)):
            db.execute(
                "INSERT INTO story_memory_revisions (id,entity_id,project_id,chapter_id,version,payload) VALUES (?,?,?,?,?,?)",
                (
                    rid,
                    str(uuid4()),
                    w.project,
                    w.chapter,
                    1,
                    json.dumps(
                        {
                            "kind": "fact",
                            "status": status,
                            "title": "事实",
                            "text": "旅人",
                            "quote": "雨",
                            "source_revision": source,
                        }
                    ),
                ),
            )
    base = {"instruction": "任务", "include_manuscript": False}
    cases = [
        ({"include_plan": True}, 422),
        ({"rule_revision_ids": [rule]}, 422),
        ({"rule_revision_ids": [str(uuid4())]}, 422),
        ({"fact_revision_ids": [proposed]}, 422),
        ({"fact_revision_ids": [fact]}, 409),
        ({"fact_revision_ids": [proposed, proposed]}, 422),
        ({"instruction": "长" * 60001}, 422),
    ]
    for extra, status in cases:
        response = w.client.post(root + "/preview", headers=w.headers, json={**base, **extra})
        assert response.status_code == status, (extra, response.text)
    assert w.client.get(root, headers=w.headers).json() == []
    assert not w.calls
