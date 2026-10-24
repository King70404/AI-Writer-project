"""Real migrated SQLite and HTTP prove author plans, plot threads, timeline and recall control."""

import json
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest
from tests.backend.test_ai_workflow import create_run, workflow
from tests.backend.test_story_memory import confirm, fact

from aiwebnovel.core.errors import AppError
from aiwebnovel.story_control.models import (
    Event,
    GoalDocument,
    RecallPolicyDocument,
    State,
    StateDocument,
    ThreadDocument,
)
from aiwebnovel.story_control.service import StoryControlService, _has_cycle
from aiwebnovel.story_control.web import get_story_control_service

__all__ = ["workflow"]


def api(w, method, path, body=None, expect=200):
    response = getattr(w.client, method)(
        f"/api/v1{path}", headers=w.headers, **({} if body is None else {"json": body})
    )
    assert response.status_code == expect, response.text
    if expect < 300:
        assert response.headers["cache-control"] == "no-store"
    return response.json()


def error(w, method, path, body=None, expect=422):
    return api(w, method, path, body, expect)["error"]["code"]


def project_path(w):
    return f"/projects/{w.project}"


def volume_of(w):
    return w.client.get(f"/api/v1/chapters/{w.chapter}").json()["volume_id"]


def add_volume(w, title, position):
    response = w.client.post(
        f"/api/v1/projects/{w.project}/volumes",
        headers=w.headers,
        json={"title": title, "summary": "", "position": position},
    )
    assert response.status_code == 201, response.text
    return response.json()["volume_id"]


def add_chapter(w, volume, title, position, content=""):
    response = w.client.post(
        f"/api/v1/projects/{w.project}/volumes/{volume}/chapters",
        headers=w.headers,
        json={"title": title, "summary": "", "position": position},
    )
    assert response.status_code == 201, response.text
    chapter = response.json()["chapter_id"]
    if content:
        set_content(w, chapter, content)
    return chapter


def set_content(w, chapter, content):
    current = w.client.get(f"/api/v1/chapters/{chapter}/content")
    response = w.client.put(
        f"/api/v1/chapters/{chapter}/content",
        headers={**w.headers, "If-Match": current.headers["etag"]},
        json={"content": content},
    )
    assert response.status_code == 200, response.text
    return response.json()["current_revision_id"]


def revision(w, chapter=None):
    return w.client.get(f"/api/v1/chapters/{chapter or w.chapter}/content").json()[
        "current_revision_id"
    ]


def goal(w, expect=201, goal_id=None, **changes):
    body = {"expected_version": 0, "scope": "book", "title": "主角夺回渡口", **changes}
    path = project_path(w) + "/arc-plans" + (f"/{goal_id}" if goal_id else "")
    return api(w, "put" if goal_id else "post", path, body, expect)


def thread(w, expect=201, thread_id=None, **changes):
    body = {"expected_version": 0, "title": "船夫的旧伤", **changes}
    path = project_path(w) + "/plot-threads" + (f"/{thread_id}" if thread_id else "")
    return api(w, "put" if thread_id else "post", path, body, expect)


def event(w, expect=201, event_id=None, **changes):
    body = {"expected_version": 0, "title": "渡口失火", **changes}
    path = project_path(w) + "/story-events" + (f"/{event_id}" if event_id else "")
    return api(w, "put" if event_id else "post", path, body, expect)


def state(w, expect=201, state_id=None, **changes):
    path = project_path(w) + "/state-intervals" + (f"/{state_id}" if state_id else "")
    return api(w, "put" if state_id else "post", path, {"expected_version": 0, **changes}, expect)


def character(w, project=None, name="船夫"):
    response = w.client.post(
        f"/api/v1/projects/{project or w.project}/characters",
        headers=w.headers,
        json={"name": name, "role": "证人", "profile": "左臂旧伤"},
    )
    assert response.status_code == 201, response.text
    return response.json()["character_id"]


def timeline(w, **params):
    response = w.client.get(f"/api/v1/projects/{w.project}/timeline", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_goal_hierarchy_links_evidence_conflicts_and_cycles(workflow):
    w = workflow
    volume = volume_of(w)
    book = goal(w, conflict="渡口被夺", outcome="")
    assert book["version"] == 1 and book["outcome"] == "" and book["status"] == "active"
    part = goal(
        w, scope="volume", volume_id=volume, title="第一卷:潜入", parent_goal_ids=[book["id"]]
    )
    later = add_chapter(w, volume, "第二章", 2, "火光照亮渡口。")
    linked = goal(
        w,
        goal_id=part["id"],
        expected_version=1,
        scope="volume",
        volume_id=volume,
        title="第一卷:潜入",
        parent_goal_ids=[book["id"]],
        links=[
            {
                "chapter_id": w.chapter,
                "status": "reflected",
                "chapter_revision_id": revision(w),
                "quote": "雨😀雨。",
            },
            {"chapter_id": later, "status": "planned", "note": "火灾后潜入"},
        ],
        expect=200,
    )
    assert linked["version"] == 2
    plan = api(w, "get", project_path(w) + "/arc-plans")
    assert [view["goal"]["id"] for view in plan["goals"]] == [book["id"], part["id"]]
    book_view, part_view = plan["goals"]
    assert book_view["child_goal_ids"] == [part["id"]]
    assert part_view["reflected"] == 1 and part_view["open_links"] == 1
    assert [link["problem"] for link in part_view["links"]] == [None, None]
    assert part_view["links"][1]["chapter_title"] == "第二章"
    # A manuscript change marks the evidence for review instead of rewriting it.
    set_content(w, w.chapter, "雨😀雨。改写后的正文。")
    part_view = api(w, "get", project_path(w) + "/arc-plans")["goals"][1]
    assert part_view["links"][0]["problem"] == "evidence_stale"
    # Saving again with the unchanged stale evidence is allowed; new evidence must be current.
    unchanged = {**{k: linked[k] for k in ("scope", "volume_id", "title", "parent_goal_ids")}}
    goal(w, goal_id=part["id"], expected_version=2, links=linked["links"], expect=200, **unchanged)
    stale_link = {**linked["links"][1], "chapter_revision_id": revision(w), "quote": "火光"}
    assert (
        error(
            w,
            "put",
            project_path(w) + f"/arc-plans/{part['id']}",
            {"expected_version": 3, **unchanged, "links": [stale_link]},
            409,
        )
        == "STORY_CONTROL_CONFLICT"
    )
    bad_quote = {**linked["links"][1], "chapter_revision_id": revision(w, later), "quote": "无此句"}
    assert (
        error(
            w,
            "put",
            project_path(w) + f"/arc-plans/{part['id']}",
            {"expected_version": 3, **unchanged, "links": [bad_quote]},
        )
        == "STORY_CONTROL_INVALID"
    )
    # Version conflicts, cycles, self-parents and unknown references are refused.
    assert goal(w, goal_id=book["id"], expected_version=0, expect=409)["error"]["code"] == (
        "STORY_CONTROL_CONFLICT"
    )
    cycle = goal(
        w, goal_id=book["id"], expected_version=1, parent_goal_ids=[part["id"]], expect=422
    )
    assert cycle["error"]["code"] == "STORY_CONTROL_CYCLE"
    selfish = goal(
        w, goal_id=book["id"], expected_version=1, parent_goal_ids=[book["id"]], expect=422
    )
    assert selfish["error"]["code"] == "STORY_CONTROL_INVALID"
    for changes in (
        {"parent_goal_ids": ["missing"]},
        {"scope": "volume", "volume_id": "vol_missing"},
        {"links": [{"chapter_id": "chp_missing"}]},
    ):
        assert goal(w, expect=422, **changes)["error"]["code"] == "STORY_CONTROL_INVALID"
    assert goal(w, goal_id="unknown", expected_version=1, expect=404)["error"]["code"] == (
        "STORY_CONTROL_NOT_FOUND"
    )
    assert goal(w, expected_version=3, expect=422)["error"]["code"] == "STORY_CONTROL_INVALID"
    for invalid in (
        {"scope": "volume"},
        {"scope": "book", "volume_id": volume},
        {"parent_goal_ids": ["a", "a"]},
        {"title": "  "},
        {"links": [{"chapter_id": w.chapter, "quote": "雨"}]},
        {"title": "坏\u0000字"},
        {"unexpected": True},
    ):
        assert goal(w, expect=422, **invalid)["error"]["code"] != "STORY_CONTROL_INVALID"
    archived = goal(w, goal_id=book["id"], expected_version=1, expect=200, status="archived")
    assert archived["status"] == "archived" and archived["created_at"] == book["created_at"]
    assert w.calls == []


def test_threads_evidence_due_todos_and_timeline_filters(workflow):
    w = workflow
    volume = volume_of(w)
    payoff = add_chapter(w, volume, "兑现章", 2)
    second_volume = add_volume(w, "第二卷", 2)
    far = add_chapter(w, second_volume, "远章", 1)
    boatman = character(w)
    foreign = character(w, api(w, "post", "/projects", {"title": "别书"}, 201)["project_id"])
    planned = thread(
        w,
        character_ids=[boatman],
        planned_setup_chapter_id=w.chapter,
        planned_payoff_chapter_id=payoff,
        priority="high",
    )
    assert planned["status"] == "planned"
    view = timeline(w)["threads"][0]
    assert view["due"] is False and view["due_reason"] is None
    guide = api(w, "get", f"/chapters/{w.chapter}/story-guide")
    assert [item["thread"]["id"] for item in guide["setup_threads"]] == [planned["id"]]
    assert (
        api(w, "get", f"/chapters/{payoff}/story-guide")["payoff_threads"][0]["thread"]["id"]
        == (planned["id"])
    )
    setup = {"role": "setup", "chapter_id": w.chapter, "chapter_revision_id": revision(w)}
    planted = thread(
        w,
        thread_id=planned["id"],
        expected_version=1,
        character_ids=[boatman],
        planned_setup_chapter_id=w.chapter,
        planned_payoff_chapter_id=payoff,
        status="planted",
        anchors=[{**setup, "quote": "雨😀雨。"}],
        expect=200,
    )
    assert planted["version"] == 2
    # Reaching the planned payoff chapter turns the open thread into a due to-do.
    set_content(w, payoff, "船夫举起左臂。")
    due = timeline(w)["threads"][0]
    assert due["due"] is True and "预计兑现章" in due["due_reason"]
    assert [
        item["thread"]["id"]
        for item in api(w, "get", f"/chapters/{far}/story-guide")["due_threads"]
    ] == [planned["id"]]
    payoff_anchor = {
        "role": "payoff",
        "chapter_id": payoff,
        "chapter_revision_id": revision(w, payoff),
        "quote": "船夫举起左臂。",
    }
    done = thread(
        w,
        thread_id=planned["id"],
        expected_version=2,
        character_ids=[boatman],
        planned_payoff_chapter_id=payoff,
        status="paid_off",
        anchors=[*planted["anchors"], payoff_anchor],
        expect=200,
    )
    assert done["status"] == "paid_off" and timeline(w)["threads"][0]["due"] is False
    # Changing the payoff text keeps the claim but marks evidence for review.
    set_content(w, payoff, "船夫放下左臂。")
    reviewed = timeline(w)["threads"][0]
    assert reviewed["evidence_stale"] is True and reviewed["due"] is True
    assert "证据待复核" in reviewed["due_reason"]
    assert [anchor["stale"] for anchor in reviewed["anchors"]] == [False, True]
    # Volume payoff becomes due when that volume's last chapter has text.
    by_volume = thread(w, title="远方来信", planned_payoff_volume_id=second_volume)
    assert (
        next(t for t in timeline(w)["threads"] if t["thread"]["id"] == by_volume["id"])["due"]
        is False
    )
    set_content(w, far, "信到了。")
    item = next(t for t in timeline(w)["threads"] if t["thread"]["id"] == by_volume["id"])
    assert "预计兑现卷" in item["due_reason"]
    empty_volume = add_volume(w, "空卷", 3)
    empty = thread(w, title="空卷伏笔", planned_payoff_volume_id=empty_volume)
    assert (
        next(t for t in timeline(w)["threads"] if t["thread"]["id"] == empty["id"])["due"] is False
    )
    abandoned = thread(w, title="弃线", status="abandoned", note="不再需要")
    assert abandoned["status"] == "abandoned"
    # Filters by status, character and volume.
    assert [t["thread"]["id"] for t in timeline(w, status="abandoned")["threads"]] == [
        abandoned["id"]
    ]
    assert [t["thread"]["id"] for t in timeline(w, character_id=boatman)["threads"]] == [
        planned["id"]
    ]
    assert {t["thread"]["id"] for t in timeline(w, volume_id=second_volume)["threads"]} == {
        by_volume["id"]
    }
    for params in (
        {"status": "unknown"},
        {"other": "x"},
        {"status": ["planned", "planted"]},
        {"volume_id": ""},
    ):
        response = w.client.get(f"/api/v1/projects/{w.project}/timeline", params=params)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_STORY_CONTROL_QUERY"
    response = w.client.get(f"/api/v1/projects/{w.project}/timeline", params={"volume_id": "nope"})
    assert response.status_code == 404
    # Invalid references and evidence rules.
    for changes, code in (
        ({"character_ids": [foreign]}, "STORY_CONTROL_INVALID"),
        ({"character_ids": ["bad id"]}, "VALIDATION"),
        ({"planned_payoff_volume_id": "vol_missing"}, "STORY_CONTROL_INVALID"),
        ({"planned_setup_chapter_id": "chp_missing"}, "STORY_CONTROL_INVALID"),
        ({"status": "planted"}, "VALIDATION"),
        ({"status": "paid_off", "anchors": [{**setup, "quote": "雨😀雨。"}]}, "VALIDATION"),
        ({"status": "abandoned"}, "VALIDATION"),
        ({"planned_payoff_chapter_id": payoff, "planned_payoff_volume_id": volume}, "VALIDATION"),
        ({"character_ids": [boatman, boatman]}, "VALIDATION"),
    ):
        body = thread(w, expect=422, **changes)
        if code != "VALIDATION":
            assert body["error"]["code"] == code
    assert w.calls == []


def test_events_story_order_reverse_narration_cycles_and_state_warnings(workflow):
    w = workflow
    volume = volume_of(w)
    second = add_chapter(w, volume, "第二章", 2, "回忆:十年前的大火。")
    boatman = character(w)
    rival = character(w, name="对手")
    fire = event(w, title="当下:渡口失火", chapter_id=w.chapter, character_ids=[boatman])
    # Narrated later (chapter 2) but happened earlier in story time.
    past = event(
        w,
        title="十年前的大火",
        chapter_id=second,
        story_time="十年前",
        before_event_ids=[fire["id"]],
        character_ids=[boatman],
    )
    loose = event(w, title="无章节事件")
    views = timeline(w)["events"]
    assert [item["event"]["id"] for item in views] == [past["id"], fire["id"], loose["id"]]
    assert [item["story_order"] for item in views] == [1, 2, 3]
    assert views[0]["narrative_position"] == [1, 2] and views[1]["narrative_position"] == [1, 1]
    assert views[2]["narrative_position"] is None and views[2]["chapter_title"] is None
    cycle = event(
        w,
        event_id=fire["id"],
        expected_version=1,
        title="当下",
        before_event_ids=[past["id"]],
        expect=422,
    )
    assert cycle["error"]["code"] == "STORY_CONTROL_CYCLE"
    for changes in (
        {"after_event_ids": ["missing"]},
        {"chapter_id": "chp_missing"},
        {"character_ids": [rival, "chr_01ARZ3NDEKTSV4RRFFQ69G5FAV"]},
    ):
        assert event(w, expect=422, **changes)["error"]["code"] == "STORY_CONTROL_INVALID"
    assert event(
        w, event_id=fire["id"], expected_version=1, after_event_ids=[fire["id"]], expect=422
    )
    assert event(w, expect=422, after_event_ids=["x"], before_event_ids=["x"])["error"]["code"]
    # Overlapping intervals of the same attribute only produce a prompt for the author.
    healed = event(w, title="伤愈", after_event_ids=[fire["id"]])
    confirmed = confirm(w, fact(w))
    injured = state(
        w,
        character_id=boatman,
        attribute="injury",
        label="左臂",
        value="烧伤",
        start_event_id=past["id"],
        end_event_id=healed["id"],
        fact_ids=[confirmed["id"]],
    )
    sound = state(
        w,
        character_id=boatman,
        attribute="injury",
        label="左臂",
        value="完好",
        start_event_id=fire["id"],
    )
    state(
        w,
        character_id=rival,
        attribute="knowledge",
        label="大火真相",
        value="不知情",
        start_event_id=past["id"],
    )
    warnings = timeline(w)["warnings"]
    assert [item["kind"] for item in warnings] == ["state_overlap"]
    assert set(warnings[0]["state_ids"]) == {injured["id"], sound["id"]}
    # Moving the second interval after the healing event resolves the overlap.
    state(
        w,
        state_id=sound["id"],
        expected_version=1,
        character_id=boatman,
        attribute="injury",
        label="左臂",
        value="完好",
        start_event_id=healed["id"],
        expect=200,
    )
    assert timeline(w)["warnings"] == []
    unknown = state(
        w,
        character_id=boatman,
        attribute="injury",
        label="左臂",
        value="骨折",
        start_event_id=loose["id"],
        end_event_id=None,
    )
    kinds = [item["kind"] for item in timeline(w)["warnings"]]
    assert kinds == ["state_order_unknown", "state_order_unknown"]
    assert timeline(w, character_id=rival)["warnings"] == []
    assert [s["state"]["id"] for s in timeline(w, character_id=boatman)["states"]] == [
        injured["id"],
        sound["id"],
        unknown["id"],
    ]
    assert [e["event"]["id"] for e in timeline(w, character_id=boatman)["events"]] == [
        past["id"],
        fire["id"],
    ]
    assert len(timeline(w, volume_id=volume)["events"]) == 2
    # Unconfirming the fact is shown on the interval rather than silently dropped.
    rejected = {k: confirmed[k] for k in ("title", "text", "quote", "source_revision")}
    response = w.client.put(
        w.base + f"/memory/facts/{confirmed['id']}",
        headers=w.headers,
        json={**rejected, "expected_version": confirmed["version"], "status": "rejected"},
    )
    assert response.status_code == 200
    first = timeline(w)["states"][0]
    assert first["invalid_fact_ids"] == [confirmed["id"]]
    base = dict(character_id=boatman, attribute="injury", label="左臂", value="x")
    for changes in (
        {"start_event_id": healed["id"], "end_event_id": past["id"]},
        {"start_event_id": "missing"},
        {"start_event_id": past["id"], "end_event_id": "missing"},
        {"start_event_id": past["id"], "fact_ids": [confirmed["id"]]},
        {"start_event_id": past["id"], "character_id": "chr_01ARZ3NDEKTSV4RRFFQ69G5FAV"},
    ):
        assert state(w, expect=422, **{**base, **changes})["error"]["code"] == (
            "STORY_CONTROL_INVALID"
        )
    assert state(w, expect=422, **base, start_event_id=past["id"], end_event_id=past["id"])
    archived = event(
        w, event_id=loose["id"], expected_version=1, title="无章节事件", archived=True, expect=200
    )
    assert archived["archived"] is True
    assert loose["id"] not in [e["event"]["id"] for e in timeline(w)["events"]]
    state(
        w,
        state_id=unknown["id"],
        expected_version=1,
        **{**base, "value": "骨折"},
        start_event_id=loose["id"],
        archived=True,
        expect=200,
    )
    assert [item["kind"] for item in timeline(w)["warnings"]] == []
    assert w.calls == []


def test_fact_search_recall_policy_preview_and_frozen_generation_context(workflow):
    w = workflow
    volume = volume_of(w)
    later = add_chapter(w, volume, "后文章节", 2, "渡口烈日当空。")
    first = confirm(w, fact(w, title="渡口天气", text="渡口正在下雨"))
    second = confirm(w, fact(w, title="船夫旧伤", text="船夫左臂有旧伤"))
    pending = fact(w, title="未确认", text="待确认的事")
    search = api(w, "get", project_path(w) + "/facts/search?q=船夫&for_chapter=" + later)
    assert [item["id"] for item in search["items"]] == [second["id"]]
    assert search["items"][0]["recallable_here"] is True and search["total"] == 1
    assert api(w, "get", project_path(w) + "/facts/search?status=pending")["total"] == 1
    page = api(w, "get", project_path(w) + f"/facts/search?chapter_id={w.chapter}&limit=1&offset=1")
    assert page["total"] == 3 and len(page["items"]) == 1 and page["offset"] == 1
    here = api(w, "get", project_path(w) + f"/facts/search?for_chapter={w.chapter}")
    assert all(item["recallable_here"] is False for item in here["items"])
    assert api(w, "get", project_path(w) + "/facts/search")["items"][0]["recallable_here"] is None
    for query in (
        "status=bad",
        "limit=0",
        "limit=101",
        "offset=-1",
        "q=" + "x" * 101,
        "x=1",
        "limit=a",
        "q=a&q=b",
    ):
        response = w.client.get(f"/api/v1/projects/{w.project}/facts/search?{query}")
        assert response.status_code == 422, query
    response = w.client.get(f"/api/v1/projects/{w.project}/facts/search?for_chapter=missing")
    assert response.status_code == 404
    policy_path = f"/chapters/{later}/recall-policy"
    assert api(w, "get", policy_path) == {
        "chapter_id": later,
        "version": 0,
        "pinned_fact_ids": [],
        "excluded_fact_ids": [],
        "updated_at": None,
    }
    # The preview never saves and never calls a model.
    preview = api(
        w,
        "post",
        f"/chapters/{later}/recall-preview",
        {"pinned_fact_ids": [second["id"]], "excluded_fact_ids": [first["id"]]},
    )
    assert [(c["id"], c["reason"]) for c in preview["selected"]] == [(second["id"], "pinned")]
    assert preview["excluded_total"] == 1 and preview["blocked"] is False
    assert preview["omitted"] == [{"id": first["id"], "title": "渡口天气", "reason": "excluded"}]
    assert preview["policy_version"] == 0 and preview["character_limit"] == 10_000
    assert api(w, "get", policy_path)["version"] == 0
    for body in (
        {"expected_version": 0, "pinned_fact_ids": [pending["id"]]},
        {"expected_version": 0, "pinned_fact_ids": ["missing"]},
        {"expected_version": 0, "excluded_fact_ids": ["missing"]},
    ):
        assert error(w, "put", policy_path, body) == "STORY_CONTROL_INVALID"
    assert error(
        w,
        "put",
        f"/chapters/{w.chapter}/recall-policy",
        {"expected_version": 0, "pinned_fact_ids": [first["id"]]},
    ) == ("STORY_CONTROL_INVALID")
    saved = api(
        w,
        "put",
        policy_path,
        {
            "expected_version": 0,
            "pinned_fact_ids": [second["id"]],
            "excluded_fact_ids": [first["id"]],
        },
    )
    assert saved["version"] == 1 and saved["updated_at"]
    assert error(w, "put", policy_path, {"expected_version": 0}, 409) == "STORY_CONTROL_CONFLICT"
    memory = w.client.get(f"/api/v1/chapters/{later}/memory").json()
    assert [item["id"] for item in memory["recalled_facts"]] == [second["id"]]
    # The prepared run freezes the pinned fact and excludes the excluded one.
    run = w.client.post(
        f"/api/v1/chapters/{later}/ai/runs", headers=w.headers, json={"profile_id": "default-local"}
    )
    assert run.status_code == 201, run.text
    sources = {item["source"]: item for item in run.json()["context"]["manifest"]["sources"]}
    assert sources["story_memory"]["references"] == [[second["id"], second["revision_id"]]]
    assert "本章召回设置第 1 版" in sources["story_memory"]["reason"]
    # Changing the source chapter makes the pin invalid: preparing is refused, not trimmed.
    set_content(w, w.chapter, "雨😀雨。新的正文。")
    blocked = api(
        w, "post", f"/chapters/{later}/recall-preview", {"pinned_fact_ids": [second["id"]]}
    )
    assert blocked["blocked"] is True
    assert blocked["omitted"][0] == {"id": second["id"], "title": "船夫旧伤", "reason": "pin_stale"}
    refused = w.client.post(
        f"/api/v1/chapters/{later}/ai/runs", headers=w.headers, json={"profile_id": "default-local"}
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "AI_RECALL_PINS_INVALID"
    assert w.client.get(f"/api/v1/chapters/{later}/memory").status_code == 200
    # Clearing the pin restores preparation; the previous run's context is unchanged.
    api(w, "put", policy_path, {"expected_version": 1})
    assert (
        w.client.get(f"/api/v1/chapters/{later}/ai/runs/{run.json()['run_id']}").json()["context"]
        == run.json()["context"]
    )
    assert w.calls == []


def test_over_budget_pins_and_invalid_pin_reasons_are_explicit(workflow):
    w = workflow
    volume = volume_of(w)
    later = add_chapter(w, volume, "后文", 2, "后文正文。")
    big = [
        confirm(w, fact(w, title=f"事实{index}", text="必须保留的前文事实" * 100))
        for index in range(12)
    ]
    pending = fact(w, title="未确认")
    rejected_source = {k: big[0][k] for k in ("title", "text", "quote", "source_revision")}
    preview = api(
        w,
        "post",
        f"/chapters/{later}/recall-preview",
        {"pinned_fact_ids": [item["id"] for item in big]},
    )
    assert preview["blocked"] is True
    reasons = {item["reason"] for item in preview["omitted"]}
    assert reasons == {"pin_over_budget"}
    assert preview["used_characters"] <= 10_000
    assert all(item["reason"] == "pinned" for item in preview["selected"])
    same_chapter = api(
        w,
        "post",
        f"/chapters/{w.chapter}/recall-preview",
        {"pinned_fact_ids": [big[0]["id"], pending["id"], "missing"]},
    )
    assert [item["reason"] for item in same_chapter["omitted"]] == [
        "pin_not_earlier",
        "pin_not_confirmed",
        "pin_missing",
    ]
    unpinned = api(w, "post", f"/chapters/{later}/recall-preview", {})
    assert unpinned["blocked"] is False and unpinned["omitted_total"] > 0
    assert {item["reason"] for item in unpinned["omitted"]} == {"budget"}
    assert rejected_source  # the facts themselves remain unchanged by previews
    assert w.calls == []


def test_story_guide_is_labelled_plan_context_and_absent_without_links(workflow):
    w = workflow
    run = create_run(w)
    assert "story_guide" not in {s["source"] for s in run["context"]["manifest"]["sources"]}
    book = goal(w, conflict="夺回渡口", obstacle="夜禁", turn="", outcome="船队归来")
    goal(
        w,
        goal_id=book["id"],
        expected_version=1,
        conflict="夺回渡口",
        obstacle="夜禁",
        outcome="船队归来",
        links=[{"chapter_id": w.chapter, "note": "主角第一次靠近渡口"}],
        expect=200,
    )
    volume_goal = goal(
        w, scope="volume", volume_id=volume_of(w), title="卷目标", links=[{"chapter_id": w.chapter}]
    )
    planned = thread(
        w,
        title="旧伤",
        content="船夫左臂",
        planned_setup_chapter_id=w.chapter,
        planned_payoff_chapter_id=w.chapter,
    )
    guide = api(w, "get", f"/chapters/{w.chapter}/story-guide")
    assert [view["goal"]["id"] for view in guide["goals"]] == [book["id"], volume_goal["id"]]
    run = create_run(w)
    sources = {s["source"]: s for s in run["context"]["manifest"]["sources"]}
    guide_source = sources["story_guide"]
    assert "不是已发生的正文事实" in guide_source["reason"]
    assert "全书目标: 主角夺回渡口" in guide_source["text"] and "阻碍: 夜禁" in guide_source["text"]
    assert "本章说明: 主角第一次靠近渡口" in guide_source["text"]
    assert "分卷目标: 卷目标" in guide_source["text"]
    assert guide_source["text"].count("旧伤") == 1
    assert [ref[0] for ref in guide_source["references"]] == [
        book["id"],
        volume_goal["id"],
        planned["id"],
    ]
    # Archived goals stop guiding; plans never become memory facts.
    goal(
        w,
        goal_id=volume_goal["id"],
        expected_version=1,
        scope="volume",
        volume_id=volume_of(w),
        title="卷目标",
        expect=200,
        status="archived",
    )
    assert len(api(w, "get", f"/chapters/{w.chapter}/story-guide")["goals"]) == 1
    assert w.client.get(w.base + "/memory").json()["facts"] == []
    assert w.calls == []


def test_guide_text_is_bounded_and_marked_truncated(workflow):
    w = workflow
    for index in range(3):
        thread(
            w,
            title=f"长伏笔{index}",
            content="很长的伏笔说明" * 280,
            planned_setup_chapter_id=w.chapter,
        )
    service = w.app.state.story_control_service
    (source,) = service.guide_sources(w.chapter)
    assert len(source.text) == 4_000 and source.truncated is True


def test_project_visibility_schema_gate_immutability_and_unavailable_service(workflow):
    w = workflow
    other = api(w, "post", "/projects", {"title": "别书"}, 201)["project_id"]
    created = goal(w)
    assert (
        api(
            w,
            "put",
            f"/projects/{other}/arc-plans/{created['id']}",
            {"expected_version": 1, "scope": "book", "title": "x"},
            404,
        )["error"]["code"]
        == "STORY_CONTROL_NOT_FOUND"
    )
    assert error(w, "get", "/projects/bad id/arc-plans", expect=422) == "INVALID_PROJECT_ID"
    assert error(w, "get", "/chapters/bad/story-guide", expect=422) == "INVALID_CHAPTER_ID"
    assert error(w, "get", "/chapters/chp_01ARZ3NDEKTSV4RRFFQ69G5FAV/story-guide", expect=404) == (
        "CHAPTER_NOT_FOUND"
    )
    with closing(sqlite3.connect(w.db)) as connection:
        for statement in (
            "UPDATE story_control_revisions SET version = 9",
            "DELETE FROM story_control_revisions",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(statement)
        payload = json.loads(
            connection.execute("SELECT payload FROM story_control_revisions").fetchone()[0]
        )
        assert payload["title"] == "主角夺回渡口" and payload["kind"] == "goal"
    project_url = f"/api/v1/projects/{w.project}"
    deleted = w.client.post(
        project_url + "/delete",
        headers={**w.headers, "If-Match": w.client.get(project_url).headers["etag"]},
    )
    assert deleted.status_code == 200
    assert error(w, "get", project_path(w) + "/arc-plans", expect=404) == "PROJECT_NOT_FOUND"
    assert goal(w, expect=404)["error"]["code"] == "PROJECT_NOT_FOUND"
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(AppError) as unavailable:
        get_story_control_service(request)
    assert unavailable.value.code == "STORY_CONTROL_UNAVAILABLE"
    request.app.state.ai_workflow_schema_required = True
    with pytest.raises(AppError) as schema:
        get_story_control_service(request)
    assert schema.value.code == "AI_WORKFLOW_SCHEMA_REQUIRED"


def test_document_validators_and_helpers_without_database():
    assert _has_cycle({"a": {"b"}, "b": {"a"}}) is True
    assert _has_cycle({"a": {"b"}}) is False
    with pytest.raises(ValueError):
        GoalDocument(scope="book", title="x", links=[{"chapter_id": "c"}, {"chapter_id": "c"}])
    with pytest.raises(ValueError):
        ThreadDocument(title="x", content="\ud800")
    with pytest.raises(ValueError):
        StateDocument(
            character_id="c",
            attribute="other",
            label="l",
            value="v",
            start_event_id="e",
            fact_ids=["f", "f"],
        )
    with pytest.raises(ValueError):
        RecallPolicyDocument(pinned_fact_ids=["a"], excluded_fact_ids=["a"])
    assert Event.model_fields["kind"].default == "event"
    assert State.model_fields["kind"].default == "state"


def test_item_limits_are_enforced_per_project(workflow, monkeypatch):
    w = workflow
    monkeypatch.setattr("aiwebnovel.story_control.service.MAX_GOALS", 1)
    first = goal(w)
    assert goal(w, expect=422)["error"]["code"] == "STORY_CONTROL_INVALID"
    goal(w, goal_id=first["id"], expected_version=1, title="仍可修改", expect=200)


def test_saved_policy_preview_without_draft_uses_saved_selection(workflow):
    w = workflow
    later = add_chapter(w, volume_of(w), "后文", 2, "后文。")
    kept = confirm(w, fact(w, title="保留"))
    api(
        w,
        "put",
        f"/chapters/{later}/recall-policy",
        {"expected_version": 0, "excluded_fact_ids": [kept["id"]]},
    )
    service: StoryControlService = w.app.state.story_control_service
    preview = service.recall_preview(later)
    assert preview.policy_version == 1 and preview.selected == [] and preview.excluded_total == 1
    assert service.selection_policy(w.chapter) is None


def test_arc_plan_lists_form_choices_with_bounded_character_pages(workflow, monkeypatch):
    w = workflow
    first, second = character(w, name="甲"), character(w, name="乙")
    monkeypatch.setattr("aiwebnovel.story_control.service.MAX_CHARACTER_LIST_LIMIT", 1)
    plan = api(w, "get", project_path(w) + "/arc-plans")
    assert {item["character_id"] for item in plan["characters"]} == {first, second}
    assert plan["volumes"] == [{"volume_id": volume_of(w), "title": "测试卷", "position": 1}]
    assert plan["chapters"][0]["chapter_id"] == w.chapter
    assert plan["chapters"][0]["revision_id"] == revision(w)
    assert "content" not in plan["chapters"][0]
    monkeypatch.setattr("aiwebnovel.story_control.service.MAX_CHARACTER_OPTIONS", 1)
    assert len(api(w, "get", project_path(w) + "/arc-plans")["characters"]) == 1
