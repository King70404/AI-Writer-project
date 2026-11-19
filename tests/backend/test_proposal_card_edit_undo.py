"""C-1/C-2 suggestion cards: author edits before adoption and undo of adopted cards.

Runs over real migrated SQLite and HTTP; only the outgoing transport is fake and no edit or
undo ever makes a model request.
"""

import sqlite3
from contextlib import closing

from tests.backend import test_foreshadow_extraction as fx
from tests.backend import test_plan_proposals as pp
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_story_control import set_content
from tests.backend.test_usage_ledger import transport, usage

from aiwebnovel.ai_writing.application.models import GeneratedText

planned = pp.planned
ranged = fx.ranged
__all__ = ["planned", "ranged", "workflow"]


def _edit(w, base, proposal, index, card, expect=200):
    body = {"expected_version": proposal["version"], "card": card}
    return pp._api(w, "put", f"/{base}/{proposal['id']}/cards/{index}", body, expect)


def _undo(w, base, proposal, index, expect=200):
    body = {"expected_version": proposal["version"], "card_index": index}
    return pp._api(w, "post", f"/{base}/{proposal['id']}/undo", body, expect)


def _revisions(w, kind):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM story_control_revisions WHERE kind = ?", (kind,)
        ).fetchone()[0]


# ---------------------------------------------------------------------------- plan proposals


def _sent_plan(w, volume, chapters, goal, monkeypatch):
    proposal = pp._prepare(w, goal["id"])
    calls = transport(monkeypatch, GeneratedText(pp._reply(volume, chapters), "fake"))
    return pp._send(w, proposal), calls


def test_plan_card_edit_keeps_original_and_adopts_the_edit(planned, monkeypatch):
    w, volume, chapters, goal = planned
    sent, calls = _sent_plan(w, volume, chapters, goal, monkeypatch)
    original = sent["cards"][0]
    edited_card = {
        **original,
        "title": "第一卷 立足·作者改",
        "conflict": "作者改写的冲突",
        "chapter_ids": [chapters[1]],
        "reason": "作者不能改模型理由",
    }
    edited = _edit(w, "plan-proposals", sent, 0, edited_card)
    assert edited["version"] == sent["version"] + 1
    assert edited["cards"][0] == original  # The model's suggestion is kept for comparison.
    assert [item["index"] for item in edited["edits"]] == [0]
    assert edited["edits"][0]["card"]["title"] == "第一卷 立足·作者改"
    assert edited["edits"][0]["card"]["reason"] == original["reason"]
    assert list(pp._goals(w)) == [goal["id"]]  # An edit writes no plan.

    # Edits follow the proposal version (stale version → conflict, nothing changes).
    stale = _edit(w, "plan-proposals", sent, 0, edited_card, expect=409)
    assert stale["error"]["code"] == "PLAN_PROPOSAL_CONFLICT"
    # An edit may not reference anything outside the frozen snapshot or change the kind.
    bad = {**edited_card, "chapter_ids": ["not-in-snapshot"]}
    invalid = _edit(w, "plan-proposals", edited, 0, bad, expect=422)
    assert invalid["error"]["code"] == "PLAN_PROPOSAL_CARD_INVALID"
    link = {"kind": "chapter_link", "chapter_id": chapters[0], "note": ""}
    kind = _edit(w, "plan-proposals", edited, 0, link, expect=422)
    assert kind["error"]["code"] == "PLAN_PROPOSAL_CARD_INVALID"

    adopted = pp._adopt(w, edited, [0])
    assert [(a["index"], a["action"], a["edited"]) for a in adopted["adoptions"]] == [
        (0, "created", True)
    ]
    child = pp._goals(w)[adopted["adoptions"][0]["goal_id"]]
    assert child["title"] == "第一卷 立足·作者改" and child["conflict"] == "作者改写的冲突"
    assert [link["chapter_id"] for link in child["links"]] == [chapters[1]]
    # An adopted card cannot be edited until it is undone.
    locked = _edit(w, "plan-proposals", adopted, 0, original, expect=409)
    assert locked["error"]["code"] == "PLAN_PROPOSAL_CONFLICT"

    # Restoring the original (card: null) removes the edit.
    restored = _edit(w, "plan-proposals", adopted, 2, {**sent["cards"][2], "note": "改"})
    assert [item["index"] for item in restored["edits"]] == [0, 2]
    reverted = _edit(w, "plan-proposals", restored, 2, None)
    assert [item["index"] for item in reverted["edits"]] == [0]
    linked = pp._adopt(w, reverted, [2])
    assert [a["edited"] for a in linked["adoptions"]] == [True, False]
    assert len(calls) == 1 and len(usage(w)["items"]) == 1


def test_plan_undo_rolls_back_created_goal_and_link_and_allows_readoption(planned, monkeypatch):
    w, volume, chapters, goal = planned
    sent, calls = _sent_plan(w, volume, chapters, goal, monkeypatch)
    adopted = pp._adopt(w, sent, [0, 2])
    child_id = adopted["adoptions"][0]["goal_id"]
    assert set(pp._goals(w)) == {goal["id"], child_id}
    assert pp._goals(w)[goal["id"]]["version"] == 2

    # Undo the link: the source goal loses exactly that link (a new revision, not a rewrite).
    unlinked = _undo(w, "plan-proposals", adopted, 2)
    source = pp._goals(w)[goal["id"]]
    assert source["links"] == [] and source["version"] == 3
    assert [(a["index"]) for a in unlinked["adoptions"]] == [0]
    assert [(u["index"], u["action"]) for u in unlinked["undos"]] == [(2, "linked")]
    assert unlinked["known_goal_version"] == 3

    # Undo the created goal: it disappears from the plan; its history gains a tombstone.
    revisions = _revisions(w, "goal")
    removed = _undo(w, "plan-proposals", unlinked, 0)
    assert list(pp._goals(w)) == [goal["id"]]
    assert _revisions(w, "goal") == revisions + 1
    assert removed["adoptions"] == [] and removed["created_goal_ids"] == []
    # Undoing a card that is not adopted is a conflict.
    again = _undo(w, "plan-proposals", removed, 0, expect=409)
    assert again["error"]["code"] == "PLAN_PROPOSAL_CONFLICT"

    # Both cards can be adopted again; the re-created goal gets a fresh id.
    readopted = pp._adopt(w, removed, [0, 2])
    new_child = readopted["adoptions"][0]["goal_id"]
    assert new_child != child_id and new_child.startswith(sent["id"])
    goals = pp._goals(w)
    assert set(goals) == {goal["id"], new_child}
    assert [link["chapter_id"] for link in goals[goal["id"]]["links"]] == [chapters[1]]
    assert len(calls) == 1


def test_plan_undo_is_refused_when_the_plan_changed_afterwards(planned, monkeypatch):
    w, volume, chapters, goal = planned
    sent, _ = _sent_plan(w, volume, chapters, goal, monkeypatch)
    adopted = pp._adopt(w, sent, [0, 1, 2])
    child_id = adopted["adoptions"][0]["goal_id"]
    other_id = adopted["adoptions"][1]["goal_id"]
    # The author edits the adopted child goal: undo must not throw that edit away.
    child = pp._goals(w)[child_id]
    pp._api(
        w,
        "put",
        f"/arc-plans/{child_id}",
        {
            **{k: child[k] for k in ("scope", "volume_id", "parent_goal_ids", "links")},
            "title": "作者又改了",
            "expected_version": child["version"],
        },
    )
    conflict = _undo(w, "plan-proposals", adopted, 0, expect=409)
    assert conflict["error"]["code"] == "PLAN_PROPOSAL_UNDO_CONFLICT"
    assert pp._goals(w)[child_id]["title"] == "作者又改了"
    # A goal the author hung under the adopted goal also blocks its retraction.
    pp._goal(w, "孙目标", parent_goal_ids=[other_id])
    blocked = _undo(w, "plan-proposals", adopted, 1, expect=409)
    assert blocked["error"]["code"] == "PLAN_PROPOSAL_UNDO_CONFLICT"
    assert other_id in pp._goals(w)
    # The author edits the source goal after the link was adopted.
    source = pp._goals(w)[goal["id"]]
    pp._api(
        w,
        "put",
        f"/arc-plans/{goal['id']}",
        {
            "scope": "book",
            "title": "作者改了全书目标",
            "links": source["links"],
            "expected_version": source["version"],
        },
    )
    linked = _undo(w, "plan-proposals", adopted, 2, expect=409)
    assert linked["error"]["code"] == "PLAN_PROPOSAL_UNDO_CONFLICT"
    assert len(pp._goals(w)[goal["id"]]["links"]) == 1
    # A stale proposal version is refused before anything is read.
    stale = _undo(w, "plan-proposals", {**adopted, "version": 1}, 2, expect=409)
    assert stale["error"]["code"] == "PLAN_PROPOSAL_CONFLICT"
    reloaded = pp._api(w, "get", f"/plan-proposals/{sent['id']}")
    assert len(reloaded["adoptions"]) == 3 and reloaded["undos"] == []


# ---------------------------------------------------------------------------- foreshadow


def _sent_extraction(w, chapters, existing, monkeypatch, bad_quote=True):
    proposal = fx._prepare(w, chapters)
    reply = fx._reply(chapters, existing["id"], bad_quote=bad_quote)
    calls = transport(monkeypatch, GeneratedText(reply, "fake"))
    return fx._send(w, proposal), calls


def test_foreshadow_edit_is_verified_and_can_repair_an_invalid_card(ranged, monkeypatch):
    w, chapters, existing = ranged
    sent, calls = _sent_extraction(w, chapters, existing, monkeypatch)
    assert [c["valid"] for c in sent["effective_checks"]] == [True, True, False]
    original = sent["cards"][2]
    # A quote that is not verbatim in the frozen chapter is refused.
    bad = _edit(w, "foreshadow-proposals", sent, 2, {**original, "quote": "并不存在的话"}, 422)
    assert bad["error"]["code"] == "FORESHADOW_CARD_INVALID"
    repaired_card = {**original, "title": "渡口火因·作者改", "quote": "夜里渡口起火。"}
    repaired = _edit(w, "foreshadow-proposals", sent, 2, repaired_card)
    assert repaired["cards"][2] == original  # Original kept for comparison.
    assert repaired["checks"][2]["problem"] == "quote_not_found"  # Original verdict kept.
    assert [c["valid"] for c in repaired["effective_checks"]] == [True, True, True]
    # An edit that duplicates an open thread's title is refused.
    clash = _edit(
        w, "foreshadow-proposals", repaired, 0, {**sent["cards"][0], "title": "少主身世"}, 422
    )
    assert clash["error"]["code"] == "FORESHADOW_CARD_INVALID"
    # Editing the payoff quote to a shorter verbatim excerpt is allowed.
    payoff = _edit(
        w, "foreshadow-proposals", repaired, 1, {**sent["cards"][1], "quote": "替少主挡下的一刀"}
    )
    assert fx._threads(w).keys() == {existing["id"]}  # Edits write no thread.

    adopted = fx._adopt(w, payoff, [1, 2])
    assert [(a["index"], a["action"], a["edited"]) for a in adopted["adoptions"]] == [
        (1, "paid_off", True),
        (2, "created", True),
    ]
    threads = fx._threads(w)
    created = threads[adopted["adoptions"][1]["thread_id"]]
    assert created["title"] == "渡口火因·作者改"
    assert created["anchors"][0]["quote"] == "夜里渡口起火。"
    assert threads[existing["id"]]["anchors"][0]["quote"] == "替少主挡下的一刀"
    locked = _edit(w, "foreshadow-proposals", adopted, 2, original, expect=409)
    assert locked["error"]["code"] == "FORESHADOW_EXTRACTION_CONFLICT"
    assert len(calls) == 1 and len(usage(w)["items"]) == 1


def test_foreshadow_undo_restores_threads_and_allows_readoption(ranged, monkeypatch):
    w, chapters, existing = ranged
    sent, calls = _sent_extraction(w, chapters, existing, monkeypatch, bad_quote=False)
    adopted = fx._adopt(w, sent, [0, 1])
    created_id = adopted["adoptions"][0]["thread_id"]
    assert fx._threads(w)[existing["id"]]["status"] == "paid_off"

    restored = _undo(w, "foreshadow-proposals", adopted, 1)
    thread = fx._threads(w)[existing["id"]]
    assert thread["status"] == "planned" and thread["anchors"] == []
    assert thread["version"] == 3 and thread["content"] == "少主不是亲生"
    removed = _undo(w, "foreshadow-proposals", restored, 0)
    assert list(fx._threads(w)) == [existing["id"]]
    assert removed["adoptions"] == []
    assert [(u["index"], u["action"]) for u in removed["undos"]] == [
        (1, "paid_off"),
        (0, "created"),
    ]
    listed = pp._api(w, "get", "/foreshadow-proposals")["items"][0]
    assert listed["adopted"] == 0

    readopted = fx._adopt(w, removed, [0, 1])
    assert readopted["adoptions"][0]["thread_id"] != created_id
    threads = fx._threads(w)
    assert len(threads) == 2 and threads[existing["id"]]["status"] == "paid_off"
    assert len(calls) == 1


def test_foreshadow_undo_is_refused_when_the_thread_changed_afterwards(ranged, monkeypatch):
    w, chapters, existing = ranged
    sent, _ = _sent_extraction(w, chapters, existing, monkeypatch, bad_quote=False)
    adopted = fx._adopt(w, sent, [0, 1])
    created_id = adopted["adoptions"][0]["thread_id"]
    created = fx._threads(w)[created_id]
    fields = ("title", "planned_setup_chapter_id", "status", "anchors")
    pp._api(
        w,
        "put",
        f"/plot-threads/{created_id}",
        {
            **{k: created[k] for k in fields},
            "content": "作者补充",
            "expected_version": created["version"],
        },
    )
    conflict = _undo(w, "foreshadow-proposals", adopted, 0, expect=409)
    assert conflict["error"]["code"] == "FORESHADOW_UNDO_CONFLICT"
    assert fx._threads(w)[created_id]["content"] == "作者补充"
    paid = fx._threads(w)[existing["id"]]
    pp._api(
        w,
        "put",
        f"/plot-threads/{existing['id']}",
        {
            "title": paid["title"],
            "content": paid["content"],
            "status": "paid_off",
            "anchors": paid["anchors"],
            "note": "作者备注",
            "expected_version": paid["version"],
        },
    )
    payoff = _undo(w, "foreshadow-proposals", adopted, 1, expect=409)
    assert payoff["error"]["code"] == "FORESHADOW_UNDO_CONFLICT"
    assert fx._threads(w)[existing["id"]]["status"] == "paid_off"
    reloaded = pp._api(w, "get", f"/foreshadow-proposals/{sent['id']}")
    assert len(reloaded["adoptions"]) == 2 and reloaded["undos"] == []


def test_retracted_thread_id_is_never_reused_and_chapter_edits_do_not_block_undo(
    ranged, monkeypatch
):
    w, chapters, existing = ranged
    sent, _ = _sent_extraction(w, chapters, existing, monkeypatch, bad_quote=False)
    adopted = fx._adopt(w, sent, [2])
    thread_id = adopted["adoptions"][0]["thread_id"]
    # Changing the chapter text later does not change the thread, so undo still works.
    set_content(w, chapters[1], fx.SECOND + "后来补的一句。")
    removed = _undo(w, "foreshadow-proposals", adopted, 2)
    assert thread_id not in fx._threads(w)
    service = w.app.state.story_control_service
    from aiwebnovel.story_control.models import SaveThread, StoryControlConflict

    try:
        service.create_thread_with_id(
            w.project, thread_id, SaveThread(title="复用", expected_version=0)
        )
    except StoryControlConflict:
        pass
    else:  # pragma: no cover - the assertion below explains the failure
        raise AssertionError("A retracted id must never be reused.")
    assert removed["adoptions"] == []
