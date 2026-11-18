"""C-3: the consistency review freezes the same per-chapter recall policy as generation.

Real migrated SQLite and HTTP; the only model transport is an in-process fake, and every
prepare step asserts that it was never called.
"""

import json
from itertools import count

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_story_control import add_chapter, api, set_content, volume_of
from tests.backend.test_story_memory import confirm, fact, provider, send

from aiwebnovel.story_memory.models import MemoryConflict, RecallSelectionPolicy, Review
from aiwebnovel.story_memory.service import StoryMemoryService

__all__ = ["workflow"]


def prepare_review(w, chapter, expect=201):
    revision = w.client.get(f"/api/v1/chapters/{chapter}/content").json()["current_revision_id"]
    response = w.client.post(
        f"/api/v1/chapters/{chapter}/memory/reviews",
        headers=w.headers,
        json={"source_revision": revision, "profile_id": "default-local"},
    )
    assert response.status_code == expect, response.text
    return response.json()


def reviews(w, chapter):
    return w.client.get(f"/api/v1/chapters/{chapter}/memory").json()["reviews"]


def test_review_freezes_pinned_first_never_sends_excluded_and_explains(workflow):
    w = workflow
    calls = provider(w)
    later = add_chapter(w, volume_of(w), "后文章节", 2, "渡口烈日当空，船夫划桨。")
    excluded = confirm(w, fact(w, title="渡口天气", text="渡口正在下雨，烈日当空的渡口"))
    pinned = confirm(w, fact(w, title="旧伤", text="左臂有旧伤"))
    related = confirm(w, fact(w, title="船夫身份", text="船夫是渡口的老船夫"))

    # Without a saved policy the review keeps the deterministic relatedness order.
    plain = prepare_review(w, later)
    assert plain["recall"]["policy_version"] == 0
    assert plain["recall"]["pinned_fact_ids"] == [] == plain["recall"]["excluded_fact_ids"]
    assert {item["reason"] for item in plain["recall"]["selected"]} == {"related"}
    assert [item["id"] for item in plain["facts"]] == [
        item["id"] for item in plain["recall"]["selected"]
    ]
    assert pinned["id"] != plain["facts"][0]["id"]  # least related without a pin

    api(
        w,
        "put",
        f"/chapters/{later}/recall-policy",
        {
            "expected_version": 0,
            "pinned_fact_ids": [pinned["id"]],
            "excluded_fact_ids": [excluded["id"]],
        },
    )
    review = prepare_review(w, later)
    assert calls == [] and w.calls == []  # preparing never transmits anything
    assert [item["id"] for item in review["facts"]] == [pinned["id"], related["id"]]
    recall = review["recall"]
    assert recall["policy_version"] == 1
    assert recall["pinned_fact_ids"] == [pinned["id"]]
    assert recall["excluded_fact_ids"] == [excluded["id"]]
    assert [(item["id"], item["reason"]) for item in recall["selected"]] == [
        (pinned["id"], "pinned"),
        (related["id"], "related"),
    ]
    assert recall["omitted"] == [{"id": excluded["id"], "title": "渡口天气", "reason": "excluded"}]
    assert recall["excluded_total"] == 1 and recall["omitted_total"] == 0
    assert recall["used_characters"] == sum(item["characters"] for item in recall["selected"])
    assert recall["character_limit"] == 10_000 and recall["item_limit"] == 24
    assert review["omitted_facts"] == 0

    # The explicit send transmits exactly the frozen facts; the excluded one never leaves.
    response = send(w, review)
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    payload = json.loads(calls[0][1][1].content)
    assert [item["id"] for item in payload["confirmed_facts"]] == [pinned["id"], related["id"]]
    assert excluded["id"] not in calls[0][1][1].content
    assert "渡口正在下雨" not in calls[0][1][1].content

    # Later policy edits do not rewrite the prepared snapshot.
    api(w, "put", f"/chapters/{later}/recall-policy", {"expected_version": 1})
    frozen = next(item for item in reviews(w, later) if item["id"] == review["id"])
    assert frozen["recall"] == recall and frozen["stale"] is False


def test_invalid_pin_refuses_review_preparation_without_model_or_review(workflow):
    w = workflow
    calls = provider(w)
    later = add_chapter(w, volume_of(w), "后文", 2, "后文正文。")
    kept = confirm(w, fact(w, title="船夫旧伤", text="船夫左臂有旧伤"))
    api(
        w,
        "put",
        f"/chapters/{later}/recall-policy",
        {"expected_version": 0, "pinned_fact_ids": [kept["id"]]},
    )
    set_content(w, w.chapter, "雨😀雨。新的正文。")  # the pinned fact's source changed
    refused = prepare_review(w, later, expect=409)
    assert refused["error"]["code"] == "AI_RECALL_PINS_INVALID"
    assert reviews(w, later) == []
    assert calls == [] and w.calls == []


def test_over_budget_pins_refuse_review_preparation(workflow):
    w = workflow
    calls = provider(w)
    later = add_chapter(w, volume_of(w), "后文", 2, "后文正文。")
    big = [
        confirm(w, fact(w, title=f"事实{index}", text="必须保留的前文事实" * 100))
        for index in range(12)
    ]
    api(
        w,
        "put",
        f"/chapters/{later}/recall-policy",
        {"expected_version": 0, "pinned_fact_ids": [item["id"] for item in big]},
    )
    refused = prepare_review(w, later, expect=409)
    assert refused["error"]["code"] == "AI_RECALL_PINS_INVALID"
    assert reviews(w, later) == []
    # Unpinning restores preparation; budget omissions are then explained, not silent.
    api(w, "put", f"/chapters/{later}/recall-policy", {"expected_version": 1})
    review = prepare_review(w, later)
    assert review["recall"]["omitted_total"] == review["omitted_facts"] > 0
    assert {item["reason"] for item in review["recall"]["omitted"]} == {"budget"}
    assert calls == [] and w.calls == []


def test_policy_change_while_preparing_is_a_conflict(workflow, monkeypatch):
    w = workflow
    provider(w)
    later = add_chapter(w, volume_of(w), "后文", 2, "后文正文。")
    service: StoryMemoryService = w.app.state.story_memory_service
    versions = count(1)  # the policy moves on between the read and the locked check
    monkeypatch.setattr(
        service, "_policy_reader", lambda _chapter: RecallSelectionPolicy(next(versions), (), ())
    )
    revision = w.client.get(f"/api/v1/chapters/{later}/content").json()["current_revision_id"]
    with pytest.raises(MemoryConflict):
        service.prepare(later, revision, "default-local")
    assert reviews(w, later) == []


def test_reviews_saved_before_c3_still_load_without_explanation():
    legacy = {
        "id": "review-1",
        "revision_id": "revision-1",
        "kind": "review",
        "project_id": "project-1",
        "chapter_id": "chapter-1",
        "version": 1,
        "source_revision": "source-1",
        "content": "正文",
        "content_truncated": False,
        "model": {"id": "m", "name": "m", "kind": "local"},
        "facts": [],
        "omitted_facts": 0,
        "status": "ready",
        "attempts": 0,
        "result": None,
        "last_error": None,
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    assert Review.model_validate(legacy).recall is None
