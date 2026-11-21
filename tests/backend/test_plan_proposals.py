"""F02 plan proposals over real migrated SQLite and HTTP; only the outgoing transport is fake."""

import json
import sqlite3
from contextlib import closing

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_candidate_edits_budget import put_budget
from tests.backend.test_story_control import add_chapter, volume_of
from tests.backend.test_usage_ledger import transport, usage

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.story_control.proposal_models import (
    PlanProposal,
    PlanProposalOutputInvalid,
)
from aiwebnovel.story_control.proposals import parse_output

__all__ = ["workflow"]


def _api(w, method, path, body=None, expect=200):
    response = getattr(w.client, method)(
        f"/api/v1/projects/{w.project}{path}",
        headers=w.headers,
        **({} if body is None else {"json": body}),
    )
    assert response.status_code == expect, response.text
    if expect < 300:
        assert response.headers["cache-control"] == "no-store"
    return response.json()


def _goal(w, title="全书目标", **values):
    body = {"scope": "book", "title": title, "expected_version": 0, **values}
    return _api(w, "post", "/arc-plans", body, 201)


def _goals(w):
    return {view["goal"]["id"]: view["goal"] for view in _api(w, "get", "/arc-plans")["goals"]}


def _prepare(w, goal_id, expect=201, **values):
    body = {"goal_id": goal_id, "profile_id": "default-local", **values}
    return _api(w, "post", "/plan-proposals", body, expect)


def _send(w, proposal, expect=200, **values):
    body = {"expected_version": proposal["version"], "cloud_consent": False, **values}
    return _api(w, "post", f"/plan-proposals/{proposal['id']}/send", body, expect)


def _adopt(w, proposal, indexes, expect=200):
    body = {"card_indexes": indexes}
    return _api(w, "post", f"/plan-proposals/{proposal['id']}/adopt", body, expect)


def _count(w, table):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _reply(volume, chapters):
    return json.dumps(
        {
            "summary": "按卷拆分",
            "cards": [
                {
                    "kind": "child_goal",
                    "title": "第一卷 立足",
                    "volume_id": volume,
                    "conflict": "主角被逐出师门",
                    "chapter_ids": [chapters[0]],
                    "reason": "开局需要落点",
                },
                {
                    "kind": "child_goal",
                    "title": "中段 反击",
                    "volume_id": None,
                    "outcome": "主角夺回名声",
                },
                {
                    "kind": "chapter_link",
                    "chapter_id": chapters[1],
                    "note": "本章揭示阴谋",
                },
            ],
        },
        ensure_ascii=False,
    )


@pytest.fixture
def planned(workflow):
    w = workflow
    volume = volume_of(w)
    second = add_chapter(w, volume, "第二章", 2)
    goal = _goal(w, conflict="正邪之争")
    return w, volume, [w.chapter, second], goal


def test_prepare_freezes_preview_without_any_model_request(planned, monkeypatch):
    w, volume, chapters, goal = planned
    calls = transport(monkeypatch)
    proposal = _prepare(w, goal["id"], author_request="拆成两段")
    assert proposal["status"] == "ready" and proposal["version"] == 1
    assert proposal["source"]["id"] == goal["id"] and proposal["source"]["version"] == 1
    assert proposal["goal_versions"] == {goal["id"]: 1}
    assert [item["chapter_id"] for item in proposal["chapters"]] == chapters
    assert proposal["volumes"][0]["volume_id"] == volume
    assert "拆成两段" in proposal["request_preview"]
    assert "雨😀雨" not in proposal["request_preview"]  # Titles only, never manuscript text.
    estimate = _api(w, "get", f"/plan-proposals/{proposal['id']}/estimate")
    assert estimate["decision"] == "allowed" and estimate["input_characters"] > 0
    listed = _api(w, "get", "/plan-proposals")
    assert [item["id"] for item in listed["items"]] == [proposal["id"]]
    assert calls == [] and usage(w)["items"] == []
    assert _prepare(w, "missing", expect=404)["error"]["code"] == "PLAN_PROPOSAL_NOT_FOUND"


def test_strict_budget_refuses_send_without_network_or_ledger(planned, monkeypatch):
    w, _, _, goal = planned
    proposal = _prepare(w, goal["id"])
    put_budget(w, task_limit="1")
    calls = transport(monkeypatch)
    estimate = _api(w, "get", f"/plan-proposals/{proposal['id']}/estimate")
    assert estimate["decision"] == "refused"
    blocked = _send(w, proposal, expect=409)
    assert blocked["error"]["code"] == "AI_BUDGET_REFUSED"
    reloaded = _api(w, "get", f"/plan-proposals/{proposal['id']}")
    assert reloaded["status"] == "ready" and reloaded["attempts"] == 0
    assert calls == [] and usage(w)["items"] == []
    assert _count(w, "model_budget_reservations") == 0


def test_valid_reply_becomes_cards_and_only_adopted_cards_change_plans(planned, monkeypatch):
    w, volume, chapters, goal = planned
    proposal = _prepare(w, goal["id"])
    calls = transport(monkeypatch, GeneratedText(_reply(volume, chapters), "fake"))
    sent = _send(w, proposal)
    assert len(calls) == 1
    assert calls[0][2].operation == "plan_proposal" and calls[0][2].task_id == proposal["id"]
    assert sent["status"] == "completed" and sent["summary"] == "按卷拆分"
    assert [card["kind"] for card in sent["cards"]] == ["child_goal", "child_goal", "chapter_link"]
    rows = usage(w)["items"]
    assert [(row["operation"], row["task_id"]) for row in rows] == [
        ("plan_proposal", proposal["id"])
    ]
    # Suggestions alone change no plan and no chapter.
    chapters_before = _count(w, "chapters")
    assert list(_goals(w)) == [goal["id"]]
    # A completed proposal is never sent again.
    assert _send(w, sent, expect=409)["error"]["code"] == "PLAN_PROPOSAL_CONFLICT"

    adopted = _adopt(w, sent, [0, 2])
    assert [(item["index"], item["action"]) for item in adopted["adoptions"]] == [
        (0, "created"),
        (2, "linked"),
    ]
    goals = _goals(w)
    assert len(goals) == 2
    child = goals[adopted["adoptions"][0]["goal_id"]]
    assert child["parent_goal_ids"] == [goal["id"]] and child["scope"] == "volume"
    assert child["volume_id"] == volume and child["title"] == "第一卷 立足"
    assert [link["chapter_id"] for link in child["links"]] == [chapters[0]]
    source = goals[goal["id"]]
    assert source["version"] == 2
    assert [(link["chapter_id"], link["note"]) for link in source["links"]] == [
        (chapters[1], "本章揭示阴谋")
    ]
    assert _count(w, "chapters") == chapters_before

    # Adopting again, alone or with a new card, never duplicates earlier adoptions.
    again = _adopt(w, adopted, [0, 2])
    assert again["adoptions"] == adopted["adoptions"]
    later = _adopt(w, adopted, [2, 1])
    assert [item["index"] for item in later["adoptions"]] == [0, 2, 1]
    goals = _goals(w)
    assert len(goals) == 3 and goals[goal["id"]]["version"] == 2
    assert len(goals[goal["id"]]["links"]) == 1
    assert len(calls) == 1
    assert _adopt(w, later, [5], expect=422)["error"]["code"] == "PLAN_PROPOSAL_INVALID"


def test_invalid_reply_fails_with_evidence_and_no_retry(planned, monkeypatch):
    w, _, _, goal = planned
    proposal = _prepare(w, goal["id"])
    raw = "好的，以下是建议 ```json {}```"
    calls = transport(monkeypatch, GeneratedText(raw, "fake"))
    failed = _send(w, proposal)
    assert failed["status"] == "failed" and failed["error"] == "PlanProposalOutputInvalid"
    assert failed["evidence"] == raw and failed["cards"] == []
    assert len(calls) == 1 and len(usage(w)["items"]) == 1
    assert _send(w, failed, expect=409)["error"]["code"] == "PLAN_PROPOSAL_CONFLICT"
    assert _adopt(w, failed, [0], expect=409)["error"]["code"] == "PLAN_PROPOSAL_CONFLICT"
    assert len(calls) == 1 and list(_goals(w)) == [goal["id"]]


def test_changed_goal_version_refuses_adoption_and_asks_to_prepare_again(planned, monkeypatch):
    w, volume, chapters, goal = planned
    proposal = _prepare(w, goal["id"])
    transport(monkeypatch, GeneratedText(_reply(volume, chapters), "fake"))
    sent = _send(w, proposal)
    changed = _api(
        w,
        "put",
        f"/arc-plans/{goal['id']}",
        {"scope": "book", "title": "作者改过的目标", "expected_version": 1},
    )
    assert changed["version"] == 2
    stale = _adopt(w, sent, [1], expect=409)
    assert stale["error"]["code"] == "PLAN_PROPOSAL_STALE"
    assert list(_goals(w)) == [goal["id"]]
    assert _api(w, "get", f"/plan-proposals/{sent['id']}")["adoptions"] == []
    # Another goal created after preparation also counts as a changed plan.
    other = _prepare(w, goal["id"])
    _goal(w, "新增目标")
    transport(monkeypatch, GeneratedText(_reply(volume, chapters), "fake"))
    resent = _send(w, other)
    assert _adopt(w, resent, [0], expect=409)["error"]["code"] == "PLAN_PROPOSAL_STALE"


def test_cloud_send_needs_consent_and_restart_fails_running_proposal(planned, monkeypatch):
    w, _, _, goal = planned
    service = w.app.state.story_control_service.proposal_service
    proposal = _prepare(w, goal["id"])
    store = service._store
    store.mutate(
        w.project,
        proposal["id"],
        1,
        lambda current: PlanProposal.model_validate(
            {**current.model_dump(), "status": "running", "attempts": 1}
        ),
    )
    store.recover_interrupted()
    recovered = _api(w, "get", f"/plan-proposals/{proposal['id']}")
    assert recovered["status"] == "failed" and recovered["error"] == "AIProviderInterrupted"
    calls = transport(monkeypatch)
    cloud = _prepare(w, goal["id"])
    stored, version = store.get(w.project, cloud["id"])
    store.mutate(
        w.project,
        cloud["id"],
        version,
        lambda current: PlanProposal.model_validate(
            {**current.model_dump(), "model": {**current.model, "kind": "cloud"}}
        ),
    )
    refused = _send(w, {**cloud, "version": version + 1}, expect=403)
    assert refused["error"]["code"] == "PLAN_PROPOSAL_CONSENT_REQUIRED"
    assert calls == [] and usage(w)["items"] == [] and stored.status == "ready"


def _frozen(chapter_ids=("c1", "c2"), linked=()):
    return PlanProposal.model_validate(
        {
            "id": "p",
            "project_id": "project",
            "goal_id": "g",
            "status": "running",
            "attempts": 1,
            "model": {"id": "m", "kind": "local"},
            "author_request": "",
            "source": {
                "id": "g",
                "version": 1,
                "scope": "volume",
                "volume_id": "v1",
                "title": "卷目标",
                "conflict": "",
                "desire": "",
                "obstacle": "",
                "turn": "",
                "outcome": "",
                "opening_state": "",
                "status": "active",
                "linked_chapter_ids": list(linked),
            },
            "children": [],
            "goal_versions": {"g": 1},
            "volumes": [{"volume_id": "v1", "title": "卷", "position": 1}],
            "chapters": [
                {
                    "chapter_id": item,
                    "volume_id": "v1",
                    "title": item,
                    "volume_position": 1,
                    "position": index + 1,
                }
                for index, item in enumerate(chapter_ids)
            ],
            "chapters_omitted": 0,
            "known_goal_version": 1,
            "created_at": "t",
            "updated_at": "t",
        }
    )


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "not json",
        '{"cards": []} trailing',
        '{"summary": "x"}',
        '{"cards": [{"kind": "rewrite_chapter", "chapter_id": "c1"}]}',
        '{"cards": [{"kind": "child_goal", "title": "x", "extra": 1}]}',
        '{"cards": [{"kind": "child_goal", "title": "' + "长" * 121 + '"}]}',
        '{"cards": [{"kind": "child_goal", "title": "x", "chapter_ids": ["c9"]}]}',
        '{"cards": [{"kind": "child_goal", "title": "x", "volume_id": "v2"}]}',
        '{"cards": [{"kind": "chapter_link", "chapter_id": "c1"}]}',
        '{"cards": [{"kind": "chapter_link", "chapter_id": "c2"},'
        ' {"kind": "chapter_link", "chapter_id": "c2"}]}',
        json.dumps({"cards": [{"kind": "child_goal", "title": f"t{i}"} for i in range(21)]}),
        '{"cards": [{"kind": "child_goal", "title": "x", "chapter_ids": ["c2", "c2"]}]}',
        '{"cards": [{"kind": "child_goal", "title": "x\\u0000"}]}',
    ],
)
def test_strict_output_schema_rejects_unbounded_or_unknown_replies(reply):
    with pytest.raises(PlanProposalOutputInvalid):
        parse_output(_frozen(linked=("c1",)), reply)


def test_strict_output_schema_accepts_bounded_cards():
    reply = json.dumps({"cards": [{"kind": "child_goal", "title": f"t{i}"} for i in range(20)]})
    assert len(parse_output(_frozen(), reply).cards) == 20
    empty = parse_output(_frozen(), ' {"summary": "无需拆分", "cards": []} ')
    assert empty.cards == [] and empty.summary == "无需拆分"
