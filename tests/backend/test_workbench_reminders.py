"""Reminder derivation is read-only and follows saved plans, evidence and usage."""

from dataclasses import replace

import pytest
from tests.backend.test_ai_workflow import workflow

__all__ = ["workflow"]

from aiwebnovel.usage.budget import Spend
from aiwebnovel.workbench.service import derive_actions
from aiwebnovel.workbench.snapshot import (
    BudgetReminderRow,
    ChapterRow,
    ProjectSnapshot,
    ThreadReminderRow,
    VolumeRow,
)

BASE = ProjectSnapshot(
    (VolumeRow("v", "卷", 1),),
    (ChapterRow("c", "v", 1, 1, "章", "revision", "now", 1),),
    {},
    {},
    (),
)
THREAD = ThreadReminderRow("thread", "计划伏笔", "planned", "c", None, ())


@pytest.mark.parametrize(
    ("status", "characters", "stale", "expected"),
    [
        ("planned", 1, False, True),
        ("planted", 1, False, True),
        ("advancing", 0, False, False),
        ("planned", 0, False, False),
        ("paid_off", 1, False, False),
        ("paid_off", 1, True, True),
        ("abandoned", 1, True, False),
        ("planned", 1, True, True),
    ],
)
def test_due_and_evidence_matrix(status, characters, stale, expected):
    thread = replace(THREAD, status=status, anchors=(("c", "old"),) if stale else ())
    snapshot = replace(
        BASE, chapters=(replace(BASE.chapters[0], characters=characters),), threads=(thread,)
    )
    actions = derive_actions(snapshot)
    assert len(actions) == int(expected)
    if expected:
        assert actions[0].kind == "due_thread" and actions[0].entity_id == "thread"
        assert actions[0].target_kind == "thread" and actions[0].count == 1


def test_volume_due_uses_last_chapter_and_entity_keys_sort_stably():
    snapshot = replace(
        BASE,
        chapters=(
            *BASE.chapters,
            replace(BASE.chapters[0], chapter_id="last", position=2, characters=0),
        ),
        threads=(replace(THREAD, payoff_chapter_id=None, payoff_volume_id="v"),),
    )
    assert derive_actions(snapshot) == []
    snapshot = replace(
        BASE, threads=(replace(THREAD, entity_id="b"), replace(THREAD, entity_id="a"))
    )
    assert [item.entity_id for item in derive_actions(snapshot)] == ["a", "b"]


@pytest.mark.parametrize(
    ("mode", "spent", "unpriced", "other", "expected"),
    [
        ("off", 100, 0, 0, False),
        ("warn", 79, 0, 0, False),
        ("warn", 80, 0, 0, True),
        ("strict", 100, 0, 0, True),
        ("strict", 0, 1, 0, True),
        ("warn", 0, 0, 1, True),
    ],
)
def test_budget_matrix(mode, spent, unpriced, other, expected):
    budget = BudgetReminderRow(mode, 100, Spend(1, spent, 0, unpriced, other))
    actions = derive_actions(replace(BASE, budget=budget))
    assert len(actions) == int(expected)
    if expected:
        assert actions[0].kind == "budget_reminder" and actions[0].chapter_id is None
        assert actions[0].target_kind == "budget" and actions[0].entity_id == "monthly-budget"


def test_persisted_thread_and_budget_sources_enter_unified_actions(workflow, monkeypatch):
    from tests.backend.test_candidate_edits_budget import put_budget, put_price
    from tests.backend.test_story_control import add_chapter, thread, volume_of
    from tests.backend.test_usage_ledger import real_provider, transport
    from tests.backend.test_workbench import actions

    from aiwebnovel.ai_writing.application.models import GeneratedText, ProviderUsage

    w = workflow
    real_provider(w)
    due = thread(w, title="兑现计划", planned_payoff_chapter_id=w.chapter)
    empty = add_chapter(w, volume_of(w), "空章", 2)
    thread(w, title="尚未到期", planned_payoff_chapter_id=empty)
    thread(
        w, title="已放弃", status="abandoned", note="作者放弃", planned_payoff_chapter_id=w.chapter
    )
    result = actions(w)
    due_items = [item for item in result["items"] if item["kind"] == "due_thread"]
    assert len(due_items) == 1 and due_items[0]["entity_id"] == due["id"]
    assert due_items[0]["target_kind"] == "thread"
    assert "content" not in due_items[0] and "anchors" not in due_items[0]
    put_price(w, inp="1", out="1")
    put_budget(w, mode="warn", monthly_limit="0.0001")
    assert all(item["kind"] != "budget_reminder" for item in actions(w)["items"])
    calls = transport(
        monkeypatch, GeneratedText("文" * 220, "workflow-test", ProviderUsage(90, 40, 130))
    )
    sent = w.client.post(w.base + "/ai/continue", json={}, headers=w.headers)
    assert sent.status_code == 200, sent.text
    assert len(calls) == 1
    reminders = [item for item in actions(w)["items"] if item["kind"] == "budget_reminder"]
    assert len(reminders) == 1 and reminders[0]["target_kind"] == "budget"
    assert reminders[0]["chapter_id"] is None
    from sqlalchemy import event
    from tests.backend.test_bookshelf_overview import overview
    from tests.backend.test_workbench import summary

    assert (
        w.client.post(
            "/api/v1/projects", headers=w.headers, json={"title": "另一本", "description": ""}
        ).status_code
        == 201
    )
    repository = w.app.state.workbench_service._repository
    with repository._sessions() as session:
        engine = session.get_bind()
    queries = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        overview(w, limit=2)
        first_count = len(queries)
        queries.clear()
        books = overview(w, limit=100)
        assert len(queries) == first_count == 12
    finally:
        event.remove(engine, "before_cursor_execute", record)
    own = next(book for book in books["items"] if book["project_id"] == w.project)
    assert own["action_total"] == summary(w)["action_total"]
    assert own["action_total"] >= 2
    put_budget(w, version=1, mode="off")
    assert all(item["kind"] != "budget_reminder" for item in actions(w)["items"])


def test_cache_discount_drives_budget_reminder_from_same_frozen_price(workflow, monkeypatch):
    from tests.backend.test_usage_ledger import real_provider, transport
    from tests.backend.test_workbench import actions

    from aiwebnovel.ai_writing.application.models import GeneratedText, ProviderUsage

    w = workflow
    real_provider(w)
    price = {
        "expected_version": 0,
        "currency": "CNY",
        "input_per_million": "2",
        "output_per_million": "4",
        "cached_input_per_million": "0.1",
    }
    assert (
        w.client.put(
            "/api/v1/ai/models/default-local/price", headers=w.headers, json=price
        ).status_code
        == 200
    )
    budget_url = f"/api/v1/projects/{w.project}/budget"
    budget = {"expected_version": 0, "mode": "warn", "currency": "CNY", "monthly_limit": "1"}
    assert w.client.put(budget_url, headers=w.headers, json=budget).status_code == 200
    calls = transport(
        monkeypatch,
        GeneratedText(
            "文" * 220, "fake", ProviderUsage(1000000, 0, 1000000, 1000000, 0, "reported")
        ),
    )
    assert w.client.post(w.base + "/ai/continue", json={}, headers=w.headers).status_code == 200
    assert len(calls) == 1
    assert w.client.get(budget_url).json()["month"]["settled"] == "0.10"
    assert all(item["kind"] != "budget_reminder" for item in actions(w)["items"])
