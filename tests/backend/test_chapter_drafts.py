"""F05 chapter drafts (``chapter_draft``) over real migrated SQLite and HTTP; only the transport
is fake. No real or paid model is ever called."""

import sqlite3
from contextlib import closing

import pytest
from tests.backend.test_ai_workflow import create_run, workflow
from tests.backend.test_candidate_edits_budget import put_budget
from tests.backend.test_story_control import set_content
from tests.backend.test_usage_ledger import transport, usage

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.ai_writing.errors import AIProviderUnavailable

__all__ = ["workflow"]

ORIGINAL = "雨😀雨。"


def segment(label: str, size: int = 220) -> str:
    text = label + "风" * (size - len(label))
    assert len(text) == size
    return text


def reply(label: str, size: int = 220) -> GeneratedText:
    return GeneratedText(segment(label, size), "fake-model")


def _call(w, method, path, body=None, expect=200):
    response = getattr(w.client, method)(
        w.base + "/ai/drafts" + path, headers=w.headers, **({} if body is None else {"json": body})
    )
    assert response.status_code == expect, response.text
    if expect < 300:
        assert response.headers["cache-control"] == "no-store"
    return response.json()


def prepare(w, expect=201, **values):
    return _call(w, "post", "", {"profile_id": "default-local", **values}, expect)


def send(w, draft, expect=200, **values):
    body = {"expected_version": draft["version"], "cloud_consent": False, **values}
    return _call(w, "post", f"/{draft['id']}/send", body, expect)


def adopt(w, draft, key, indexes=None, expect=200):
    body = {"idempotency_key": key}
    if indexes is not None:
        body["segment_indexes"] = indexes
    return _call(w, "post", f"/{draft['id']}/adopt", body, expect)


def content(w):
    return w.client.get(w.base + "/content").json()["content"]


def count(w, sql):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute(sql).fetchone()[0]


def test_prepare_list_and_estimate_make_no_model_request(workflow, monkeypatch):
    w = workflow
    calls = transport(monkeypatch)
    draft = prepare(w, instruction="写渡口夜戏", max_segments=4, max_output_characters=900)
    assert draft["status"] == "ready" and draft["version"] == 1 and draft["can_send"]
    assert draft["remaining_requests"] == 4 and draft["remaining_characters"] == 900
    assert draft["segments"] == [] and draft["attempts"] == 0
    assert "current_chapter" in draft["included_sources"]
    assert "写渡口夜戏" in draft["next_request_preview"]
    assert "本次候选稿" in draft["next_request_preview"]
    estimate = _call(w, "get", f"/{draft['id']}/estimate")
    assert estimate["decision"] == "allowed" and estimate["input_characters"] > 0
    listed = _call(w, "get", "")
    assert [item["id"] for item in listed["items"]] == [draft["id"]]
    assert calls == [] and w.calls == [] and usage(w)["items"] == []
    assert content(w) == ORIGINAL
    # Quota bounds are the draft's own contract: at most 10 requests / 3000 characters.
    assert prepare(w, expect=422, max_segments=11)
    assert prepare(w, expect=422, max_output_characters=3001)
    assert prepare(w, expect=422, max_output_characters=199)


def test_strict_budget_refuses_without_network_ledger_or_quota(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    put_budget(w, task_limit="1")
    calls = transport(monkeypatch)
    assert _call(w, "get", f"/{draft['id']}/estimate")["decision"] == "refused"
    refused = send(w, draft, expect=409, segments=3)
    assert refused["error"]["code"] == "AI_BUDGET_REFUSED"
    reloaded = _call(w, "get", f"/{draft['id']}")
    assert reloaded["status"] == "ready" and reloaded["attempts"] == 0
    assert reloaded["last_error"] == "BudgetRefused" and reloaded["segments"] == []
    assert calls == [] and usage(w)["items"] == []
    assert count(w, "SELECT COUNT(*) FROM model_budget_reservations") == 0


def test_segments_chain_with_earlier_text_only_as_draft_context(workflow, monkeypatch):
    w = workflow
    draft = prepare(w, max_segments=5)
    calls = transport(monkeypatch, reply("甲段"), reply("乙段"), reply("丙段"))
    sent = send(w, draft, segments=3)
    assert len(calls) == 3
    assert [call[2].operation for call in calls] == ["chapter_draft"] * 3
    assert {call[2].task_id for call in calls} == {draft["id"]}
    first, second, third = (call[1] for call in calls)
    draft_context = [
        message.content for message in second if message.content.startswith("本次候选稿")
    ]
    assert len(draft_context) == 1 and segment("甲段") in draft_context[0]
    assert [message.content for message in second if segment("甲段") in message.content] == (
        draft_context
    )
    assert all(segment("甲段") not in message.content for message in first)
    assert any(segment("乙段") in message.content for message in third)
    # Draft text is labelled as unadopted candidate text, never as the chapter context.
    context = next(message.content for message in third if message.content.startswith("小说上下文"))
    assert segment("甲段") not in context
    assert sent["status"] == "ready" and sent["attempts"] == 3
    assert [item["text"] for item in sent["segments"]] == [
        segment("甲段"),
        segment("乙段"),
        segment("丙段"),
    ]
    assert sent["generated_characters"] == 660 and sent["remaining_requests"] == 2
    rows = usage(w)["items"]
    assert [(row["operation"], row["task_id"]) for row in rows] == [
        ("chapter_draft", draft["id"])
    ] * 3
    assert content(w) == ORIGINAL  # Nothing is written before the author adopts.


def test_quota_exhaustion_stops_at_the_exact_segment(workflow, monkeypatch):
    w = workflow
    draft = prepare(w, max_segments=2)
    calls = transport(monkeypatch, reply("一"), reply("二"), reply("三"))
    sent = send(w, draft, segments=5)
    assert len(calls) == 2 and sent["status"] == "exhausted" and not sent["can_send"]
    assert send(w, sent, expect=409)["error"]["code"] == "CHAPTER_DRAFT_CONFLICT"
    assert len(calls) == 2
    # The character quota also stops the draft once fewer than 200 characters remain.
    small = prepare(w, max_output_characters=450)
    calls = transport(monkeypatch, reply("A", 250), reply("B", 300), reply("C"))
    sent = send(w, small, segments=3)
    # The second request may produce at most 200 characters, so a 300-character reply fails.
    assert len(calls) == 2 and sent["status"] == "failed"
    assert sent["failures"][0]["error"] == "ChapterDraftOutputInvalid"
    assert sent["remaining_requests"] == 8 and sent["remaining_characters"] == 200


def test_failure_stops_keeps_evidence_and_retry_is_explicit(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    calls = transport(monkeypatch, reply("好段"), GeneratedText("太短", "fake-model"))
    sent = send(w, draft, segments=4)
    assert len(calls) == 2  # No third request and no automatic retry.
    assert sent["status"] == "failed" and len(sent["segments"]) == 1
    failure = sent["failures"][0]
    assert failure["error"] == "ChapterDraftOutputInvalid" and failure["evidence"] == "太短"
    assert sent["attempts"] == 2 and sent["can_send"]
    # A provider error is recorded without its text; still nothing is retried.
    calls = transport(monkeypatch, AIProviderUnavailable())
    failed = send(w, sent, expect=502)
    assert failed["error"]["code"] == "AI_PROVIDER_UNAVAILABLE" and len(calls) == 1
    reloaded = _call(w, "get", f"/{draft['id']}")
    assert reloaded["status"] == "failed" and reloaded["attempts"] == 3
    assert reloaded["failures"][-1] == {
        **reloaded["failures"][-1],
        "error": "AIProviderUnavailable",
        "evidence": None,
    }
    # The author explicitly continues within quota: a new attempt, a new ledger row.
    calls = transport(monkeypatch, reply("续段"))
    resumed = send(w, reloaded)
    assert len(calls) == 1 and resumed["status"] == "ready" and resumed["attempts"] == 4
    assert [item["attempt"] for item in resumed["segments"]] == [1, 4]
    assert len(usage(w)["items"]) == 4


def test_adopt_one_segment_then_whole_draft_idempotently(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    transport(monkeypatch, reply("甲"), reply("乙"), reply("丙"))
    sent = send(w, draft, segments=3)
    revisions = count(w, "SELECT COUNT(*) FROM chapter_revisions")
    assert adopt(w, sent, "key-one-segment", [2, 1], expect=422)
    assert adopt(w, sent, "key-one-segment", [7], expect=422)
    one = adopt(w, sent, "key-one-segment", [0])
    assert content(w) == ORIGINAL + "\n\n" + segment("甲")
    assert [item["status"] for item in one["segments"]] == ["adopted", "pending", "pending"]
    assert one["current_revision_id"] != sent["current_revision_id"]
    # Replaying the same receipt changes nothing; reusing it for other segments conflicts.
    assert adopt(w, sent, "key-one-segment", [0])["receipts"] == one["receipts"]
    assert adopt(w, sent, "key-one-segment", [1], expect=409)["error"]["code"] == (
        "CHAPTER_DRAFT_CONFLICT"
    )
    assert count(w, "SELECT COUNT(*) FROM chapter_revisions") == revisions + 1
    whole = adopt(w, sent, "key-whole-draft")
    assert whole["receipts"][-1]["segment_indexes"] == [1, 2]
    assert content(w) == "\n\n".join([ORIGINAL, segment("甲"), segment("乙"), segment("丙")])
    assert adopt(w, sent, "key-whole-draft")["receipts"] == whole["receipts"]
    assert adopt(w, sent, "key-nothing-left", expect=422)
    assert count(w, "SELECT COUNT(*) FROM chapter_revisions") == revisions + 2


def test_hand_edit_since_baseline_refuses_adoption_and_keeps_draft(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    transport(monkeypatch, reply("甲"))
    sent = send(w, draft)
    set_content(w, w.chapter, ORIGINAL + "作者手改。")
    refused = adopt(w, sent, "key-after-hand-edit", expect=409)
    assert refused["error"]["code"] == "CHAPTER_DRAFT_STALE"
    assert content(w) == ORIGINAL + "作者手改。"
    kept = _call(w, "get", f"/{draft['id']}")
    assert [item["status"] for item in kept["segments"]] == ["pending"]
    assert kept["receipts"] == [] and kept["segments"][0]["text"] == segment("甲")
    # Sending on the stale dependency is refused before any request.
    calls = transport(monkeypatch, reply("乙"))
    assert send(w, kept, expect=409)["error"]["code"] == "CHAPTER_DRAFT_STALE"
    assert calls == [] and _call(w, "get", f"/{draft['id']}")["attempts"] == 1


def test_draft_text_never_reaches_other_tasks_or_facts(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    transport(monkeypatch, reply("秘密候选"))
    send(w, draft)
    secret = segment("秘密候选")
    run = create_run(w)
    assert secret not in run["context"]["text"]
    generated = w.client.post(
        w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
    )
    assert generated.status_code == 200, generated.text
    assert all(secret not in message.content for message in w.calls[-1][1])
    second = prepare(w)
    assert secret not in second["next_request_preview"]
    facts = w.client.get(f"/api/v1/projects/{w.project}/facts/search?q=秘密候选")
    assert facts.status_code == 200, facts.text
    assert facts.json()["total"] == 0
    memory = w.client.get(w.base + "/memory")
    assert memory.status_code == 200, memory.text
    assert "秘密候选" not in memory.text
    assert content(w) == ORIGINAL


def test_job_bound_draft_consumes_job_quota(workflow, monkeypatch):
    w = workflow
    job = w.client.post(
        f"/api/v1/projects/{w.project}/writing-jobs",
        headers=w.headers,
        json={"title": "候选稿任务", "chapter_ids": [w.chapter], "max_requests": 1},
    ).json()
    path = f"/api/v1/writing-jobs/{job['job_id']}"
    draft = prepare(w, writing_job_id=job["job_id"])
    assert draft["writing_job_id"] == job["job_id"]
    bound = w.client.get(path).json()
    assert bound["active_run_id"] == draft["id"] and bound["active_draft_id"] == draft["id"]
    # One step binds once; a second draft cannot take the same step.
    assert prepare(w, expect=409, writing_job_id=job["job_id"])
    calls = transport(monkeypatch, reply("甲"), reply("乙"))
    sent = send(w, draft, segments=2)
    assert len(calls) == 1 and len(sent["segments"]) == 1
    after = w.client.get(path).json()
    assert after["claimed_requests"] == 1 and after["used_characters"] == 220
    assert after["generated_characters"] == 220 and after["adopted_characters"] == 0
    refused = send(w, sent, expect=409)
    assert refused["error"]["code"] == "AI_WORKFLOW_CONFLICT" and len(calls) == 1
    adopt(w, sent, "job-draft-adopt", [0])
    assert w.client.get(path).json()["adopted_characters"] == 220


def test_restart_fails_a_running_draft_without_resending(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    with closing(sqlite3.connect(w.db)) as connection:
        connection.execute(
            "UPDATE chapter_drafts SET payload = json_set(payload, '$.status', 'running', "
            "'$.attempts', 1) WHERE id = ?",
            (draft["id"],),
        )
        connection.commit()
    calls = transport(monkeypatch)
    w.service.chapter_drafts.recover_interrupted()
    recovered = _call(w, "get", f"/{draft['id']}")
    assert recovered["status"] == "failed" and recovered["last_error"] == "AIProviderInterrupted"
    assert recovered["attempts"] == 1 and calls == []


def test_cloud_model_requires_consent(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    with closing(sqlite3.connect(w.db)) as connection:
        connection.execute(
            "UPDATE chapter_drafts SET payload = json_set(payload, '$.model.kind', 'cloud') "
            "WHERE id = ?",
            (draft["id"],),
        )
        connection.commit()
    calls = transport(monkeypatch)
    refused = send(w, draft, expect=403)
    assert refused["error"]["code"] == "CHAPTER_DRAFT_CONSENT_REQUIRED" and calls == []


@pytest.mark.integration
def test_migration_adds_ledger_operation_and_downgrade_keeps_records(tmp_path):
    from tests.backend.test_novel_structure_migration import _run_alembic

    path = tmp_path / "data" / "aiwebnovel.sqlite3"
    path.parent.mkdir()

    def objects(sql):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute(sql).fetchall()

    def triggers():
        return sorted(
            objects(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name IN "
                "('model_usage_attempts', 'model_budget_reservations')"
            )
        )

    assert _run_alembic(path, "upgrade", "0023_add_foreshadow_proposals").returncode == 0
    before = triggers()
    upgraded = _run_alembic(path, "upgrade", "0024_add_chapter_drafts")
    assert upgraded.returncode == 0, upgraded.stderr
    ledger = objects("SELECT sql FROM sqlite_master WHERE name='model_usage_attempts'")[0][0]
    assert "'chapter_draft'" in ledger and "'foreshadow_extraction'" in ledger
    assert triggers() == before and before
    assert objects("SELECT version_num FROM alembic_version") == [("0024_add_chapter_drafts",)]
    down = _run_alembic(path, "downgrade", "0023_add_foreshadow_proposals")
    assert down.returncode == 0, down.stderr
    assert objects("SELECT name FROM sqlite_master WHERE name='chapter_drafts'") == []
    assert triggers() == before
    assert _run_alembic(path, "upgrade", "0024_add_chapter_drafts").returncode == 0
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO chapter_drafts (id, project_id, chapter_id, created_at, version, payload)"
            " VALUES ('d', 'x', 'c', 't', 1, '{}')"
        )
        connection.commit()
    refused = _run_alembic(path, "downgrade", "0023_add_foreshadow_proposals")
    assert refused.returncode != 0 and "must be retained" in refused.stderr


def change(w, draft, index, action, text=None, expect=200, version=None):
    body = {"expected_version": draft["version"] if version is None else version, "action": action}
    if text is not None:
        body["text"] = text
    return _call(w, "post", f"/{draft['id']}/segments/{index}", body, expect)


def test_edit_discard_and_restore_segments_without_model_or_chapter_write(workflow, monkeypatch):
    w = workflow
    draft = prepare(w, max_segments=5)
    transport(monkeypatch, reply("甲"), reply("乙"), reply("丙"))
    sent = send(w, draft, segments=3)
    revisions = count(w, "SELECT COUNT(*) FROM chapter_revisions")
    attempts = len(usage(w)["items"])
    calls = transport(monkeypatch)
    edited_text = "作者改写的第一段。"
    edited = change(w, sent, 0, "edit", edited_text)
    first = edited["segments"][0]
    assert first["text"] == segment("甲") and first["edited_text"] == edited_text
    assert first["edited_characters"] == 9 and first["status"] == "pending"
    assert edited["version"] == sent["version"] + 1
    # A stale version is refused; nothing changes.
    assert change(w, sent, 1, "discard", expect=409)["error"]["code"] == "CHAPTER_DRAFT_CONFLICT"
    discarded = change(w, edited, 1, "discard")
    assert [item["status"] for item in discarded["segments"]] == ["pending", "discarded", "pending"]
    # The next request sees the author's edit and never the discarded segment.
    preview = discarded["next_request_preview"]
    assert edited_text in preview and segment("甲") not in preview
    assert segment("乙") not in preview and segment("丙") in preview
    # Quota already used is never returned by editing or discarding.
    assert discarded["attempts"] == 3 and discarded["generated_characters"] == 660
    # Invalid changes: missing/extra text, blank text, wrong state or index.
    assert change(w, discarded, 2, "edit", expect=422)
    assert change(w, discarded, 2, "discard", "多余", expect=422)
    assert change(w, discarded, 2, "edit", "  \n ", expect=422)
    assert change(w, discarded, 1, "edit", "改已丢弃段", expect=422)
    assert change(w, discarded, 0, "restore", expect=422)
    assert change(w, discarded, 9, "discard", expect=422)
    # A discarded segment cannot be adopted.
    assert adopt(w, discarded, "key-discarded", [1], expect=422)
    whole = adopt(w, discarded, "key-edited-whole")
    assert whole["receipts"][-1]["segment_indexes"] == [0, 2]
    assert content(w) == "\n\n".join([ORIGINAL, edited_text, segment("丙")])
    assert [item["status"] for item in whole["segments"]] == ["adopted", "discarded", "adopted"]
    # Adopted segments are final; a discarded one can still be restored and adopted later.
    assert change(w, whole, 0, "edit", "再改", expect=422)
    restored = change(w, whole, 1, "restore")
    assert restored["segments"][1]["status"] == "pending"
    assert restored["segments"][1]["discarded_at"] is None
    assert count(w, "SELECT COUNT(*) FROM chapter_revisions") == revisions + 1
    assert calls == [] and len(usage(w)["items"]) == attempts
    listed = _call(w, "get", "")["items"][0]
    assert (listed["adopted"], listed["discarded"], listed["edited"]) == (2, 0, 1)


def test_editing_back_to_the_original_removes_the_edit(workflow, monkeypatch):
    w = workflow
    draft = prepare(w)
    transport(monkeypatch, reply("甲"))
    sent = send(w, draft)
    edited = change(w, sent, 0, "edit", "改一下")
    reverted = change(w, edited, 0, "edit", segment("甲"))
    first = reverted["segments"][0]
    assert first["edited_text"] is None and first["edited_characters"] is None
    assert _call(w, "get", "")["items"][0]["edited"] == 0
    # A whitespace-only replacement is refused before the store is touched.
    assert change(w, reverted, 0, "edit", "\u3000", expect=422)


def test_writing_job_lists_its_drafts_and_counts_edited_adoption(workflow, monkeypatch):
    w = workflow
    job = w.client.post(
        f"/api/v1/projects/{w.project}/writing-jobs",
        headers=w.headers,
        json={"title": "候选稿抽屉", "chapter_ids": [w.chapter], "max_requests": 3},
    ).json()
    path = f"/api/v1/writing-jobs/{job['job_id']}"
    assert w.client.get(path).json()["drafts"] == []
    draft = prepare(w, writing_job_id=job["job_id"])
    transport(monkeypatch, reply("甲"), reply("乙"))
    sent = send(w, draft, segments=2)
    edited = change(w, sent, 0, "edit", "作者改短。")
    discarded = change(w, edited, 1, "discard")
    adopt(w, discarded, "job-drawer-adopt")
    listed = w.client.get(path).json()
    assert listed["drafts"] == [
        {
            "draft_id": draft["id"],
            "chapter_id": w.chapter,
            "step_index": 0,
            "status": "ready",
            "segments": 2,
            "pending": 0,
            "adopted": 1,
            "discarded": 1,
            "edited": 1,
            "generated_characters": 440,
            "adopted_characters": 5,
            "created_at": listed["drafts"][0]["created_at"],
        }
    ]
    assert listed["adopted_characters"] == 5 and listed["generated_characters"] == 440
    # The job summary carries counts only, never segment text.
    assert segment("甲") not in str(listed) and "作者改短" not in str(listed)
    projects = w.client.get(f"/api/v1/projects/{w.project}/writing-jobs").json()
    assert projects[0]["drafts"][0]["draft_id"] == draft["id"]
