"""F03 batch event/state extraction over real migrated SQLite and HTTP; only transport is fake."""

import json
import sqlite3
from contextlib import closing

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_candidate_edits_budget import put_budget
from tests.backend.test_story_control import add_chapter, character, set_content, volume_of
from tests.backend.test_usage_ledger import transport, usage

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.story_control.timeline_extraction import parse_output
from aiwebnovel.story_control.timeline_extraction_models import (
    TimelineOutputInvalid,
    TimelineProposal,
)

__all__ = ["workflow"]

FIRST = "雨😀雨。船夫左臂中了一刀，血染红了旧布。"
SECOND = "三日后，船夫的伤口结了痂，他已能单手撑船。少主在灯下认出了他。"


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


def _timeline(w):
    return _api(w, "get", "/timeline")


def _events(w):
    return {view["event"]["id"]: view["event"] for view in _timeline(w)["events"]}


def _states(w):
    return {view["state"]["id"]: view["state"] for view in _timeline(w)["states"]}


def _prepare(w, chapters, expect=201, **values):
    body = {"chapter_ids": chapters, "profile_id": "default-local", **values}
    return _api(w, "post", "/timeline-proposals", body, expect)


def _send(w, proposal, expect=200, **values):
    body = {"expected_version": proposal["version"], "cloud_consent": False, **values}
    return _api(w, "post", f"/timeline-proposals/{proposal['id']}/send", body, expect)


def _adopt(w, proposal, indexes, expect=200):
    body = {"card_indexes": indexes}
    return _api(w, "post", f"/timeline-proposals/{proposal['id']}/adopt", body, expect)


def _count(w, table):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.fixture
def ranged(workflow):
    w = workflow
    set_content(w, w.chapter, FIRST)
    second = add_chapter(w, volume_of(w), "第二章", 2, SECOND)
    boatman = character(w)
    existing = _api(w, "post", "/story-events", {"expected_version": 0, "title": "离开渡口"}, 201)
    old_state = _api(
        w,
        "post",
        "/state-intervals",
        {
            "expected_version": 0,
            "character_id": boatman,
            "attribute": "injury",
            "label": "左臂伤势",
            "value": "完好",
            "start_event_id": existing["id"],
        },
        201,
    )
    return w, [w.chapter, second], boatman, existing, old_state


def _reply(chapters, boatman, existing, old_state, *, bad_quote=False):
    return json.dumps(
        {
            "summary": "一次受伤、一次伤愈",
            "cards": [
                {
                    "kind": "event",
                    "title": "渡口遇袭",
                    "description": "船夫左臂中刀",
                    "chapter_id": chapters[0],
                    "character_ids": [boatman],
                    "after_event_ids": [existing["id"]],
                    "quote": "船夫左臂中了一刀，血染红了旧布。",
                    "reason": "受伤",
                },
                {
                    "kind": "state",
                    "character_id": boatman,
                    "attribute": "injury",
                    "label": "左臂伤势",
                    "value": "刀伤未愈",
                    "chapter_id": chapters[0],
                    "start_event_card": 0,
                    "ends_state_id": old_state["id"],
                    "quote": "船夫左臂中了一刀",
                },
                {
                    "kind": "event",
                    "title": "少主认人",
                    "story_time": "三日后",
                    "chapter_id": chapters[1],
                    "quote": "少主在灯下认出了他" + ("，泪如雨下" if bad_quote else "。"),
                },
                {
                    "kind": "state",
                    "character_id": boatman,
                    "attribute": "knowledge",
                    "label": "身份",
                    "value": "被少主认出",
                    "chapter_id": chapters[1],
                    "start_event_id": existing["id"],
                    "quote": "少主在灯下认出了他。",
                },
            ],
        },
        ensure_ascii=False,
    )


def test_preview_and_prepare_freeze_range_without_any_model_request(ranged, monkeypatch):
    w, chapters, boatman, existing, old_state = ranged
    calls = transport(monkeypatch)
    preview = _api(w, "post", "/timeline-proposals/preview", {"chapter_ids": chapters[::-1]})
    assert [item["chapter_id"] for item in preview["chapters"]] == chapters  # Book order.
    assert preview["total_characters"] == len(FIRST) + len(SECOND)
    assert (preview["characters"], preview["events"], preview["open_states"]) == (1, 1, 1)
    assert preview["problem"] is None
    proposal = _prepare(w, chapters, author_request="只看伤势")
    assert proposal["status"] == "ready" and proposal["version"] == 1
    assert "content" not in proposal["chapters"][0]
    assert [item["character_id"] for item in proposal["characters"]] == [boatman]
    assert [item["id"] for item in proposal["events"]] == [existing["id"]]
    assert [item["id"] for item in proposal["states"]] == [old_state["id"]]
    assert FIRST in proposal["request_preview"] and "只看伤势" in proposal["request_preview"]
    estimate = _api(w, "get", f"/timeline-proposals/{proposal['id']}/estimate")
    assert estimate["decision"] == "allowed" and estimate["input_characters"] > len(FIRST)
    listed = _api(w, "get", "/timeline-proposals")
    assert [item["id"] for item in listed["items"]] == [proposal["id"]]
    assert calls == [] and usage(w)["items"] == []


def test_range_bounds_are_refused_before_anything_is_stored(ranged, monkeypatch):
    w, chapters, *_ = ranged
    calls = transport(monkeypatch)
    empty = add_chapter(w, volume_of(w), "空章", 3)
    preview = _api(w, "post", "/timeline-proposals/preview", {"chapter_ids": [empty]})
    assert preview["problem"] == "empty_chapter"
    assert _prepare(w, [empty], expect=422)["error"]["code"] == "TIMELINE_EXTRACTION_INVALID"
    assert _prepare(w, ["missing"], expect=422)["error"]["code"] == ("TIMELINE_EXTRACTION_INVALID")
    assert _prepare(w, [chapters[0], chapters[0]], expect=422)
    assert calls == [] and _count(w, "timeline_proposals") == 0


def test_strict_budget_refuses_send_without_network_or_ledger(ranged, monkeypatch):
    w, chapters, *_ = ranged
    proposal = _prepare(w, chapters)
    put_budget(w, task_limit="1")
    calls = transport(monkeypatch)
    assert _api(w, "get", f"/timeline-proposals/{proposal['id']}/estimate")["decision"] == (
        "refused"
    )
    assert _send(w, proposal, expect=409)["error"]["code"] == "AI_BUDGET_REFUSED"
    reloaded = _api(w, "get", f"/timeline-proposals/{proposal['id']}")
    assert reloaded["status"] == "ready" and reloaded["attempts"] == 0
    assert calls == [] and usage(w)["items"] == []
    assert _count(w, "model_budget_reservations") == 0


def test_cards_are_checked_and_only_adopted_cards_write_events_and_states(ranged, monkeypatch):
    w, chapters, boatman, existing, old_state = ranged
    proposal = _prepare(w, chapters)
    reply = _reply(chapters, boatman, existing, old_state, bad_quote=True)
    calls = transport(monkeypatch, GeneratedText(reply, "fake"))
    sent = _send(w, proposal)
    assert len(calls) == 1
    assert calls[0][2].operation == "timeline_extraction"
    assert calls[0][2].task_id == proposal["id"]
    assert sent["status"] == "completed"
    assert [card["kind"] for card in sent["cards"]] == ["event", "state", "event", "state"]
    assert [check["valid"] for check in sent["checks"]] == [True, True, False, True]
    assert sent["checks"][2]["problem"] == "quote_not_found"
    assert [(r["operation"], r["task_id"]) for r in usage(w)["items"]] == [
        ("timeline_extraction", proposal["id"])
    ]
    # Suggestions alone change no event, no state and no chapter.
    assert list(_events(w)) == [existing["id"]] and list(_states(w)) == [old_state["id"]]
    assert _send(w, sent, expect=409)["error"]["code"] == "TIMELINE_EXTRACTION_CONFLICT"
    assert _adopt(w, sent, [2], expect=422)["error"]["code"] == "TIMELINE_CARD_INVALID"
    # A state that starts at a suggested event needs that event card adopted or selected.
    needs = _adopt(w, sent, [1], expect=422)
    assert needs["error"]["code"] == "TIMELINE_CARD_NEEDS_EVENT"
    assert list(_events(w)) == [existing["id"]]

    adopted = _adopt(w, sent, [1, 0])
    assert [(item["index"], item["action"]) for item in adopted["adoptions"]] == [
        (0, "event_created"),
        (1, "state_created"),
    ]
    event_id = adopted["adoptions"][0]["target_id"]
    state_id = adopted["adoptions"][1]["target_id"]
    assert adopted["adoptions"][1]["ended_state_id"] == old_state["id"]
    events = _events(w)
    assert events[event_id]["title"] == "渡口遇袭"
    assert events[event_id]["chapter_id"] == chapters[0]
    assert events[event_id]["character_ids"] == [boatman]
    assert events[event_id]["after_event_ids"] == [existing["id"]]
    states = _states(w)
    assert states[state_id]["start_event_id"] == event_id
    assert states[state_id]["value"] == "刀伤未愈" and states[state_id]["end_event_id"] is None
    assert states[old_state["id"]]["end_event_id"] == event_id
    assert states[old_state["id"]]["version"] == 2
    assert _timeline(w)["warnings"] == []

    # Adopting again never duplicates; a later subset adds only the new card.
    assert _adopt(w, adopted, [0, 1])["adoptions"] == adopted["adoptions"]
    later = _adopt(w, adopted, [3])
    assert [item["index"] for item in later["adoptions"]] == [0, 1, 3]
    assert len(_events(w)) == 2 and len(_states(w)) == 3
    assert _states(w)[old_state["id"]]["version"] == 2
    assert len(calls) == 1
    assert _adopt(w, later, [7], expect=422)["error"]["code"] == "TIMELINE_EXTRACTION_INVALID"


def test_invalid_reply_fails_with_evidence_and_no_retry(ranged, monkeypatch):
    w, chapters, _, existing, _ = ranged
    proposal = _prepare(w, chapters)
    raw = "好的 ```json {}```"
    calls = transport(monkeypatch, GeneratedText(raw, "fake"))
    failed = _send(w, proposal)
    assert failed["status"] == "failed" and failed["error"] == "TimelineOutputInvalid"
    assert failed["evidence"] == raw and failed["cards"] == []
    assert _send(w, failed, expect=409)["error"]["code"] == "TIMELINE_EXTRACTION_CONFLICT"
    assert _adopt(w, failed, [0], expect=409)["error"]["code"] == "TIMELINE_EXTRACTION_CONFLICT"
    assert len(calls) == 1 and list(_events(w)) == [existing["id"]]


def test_changed_chapter_or_ended_state_refuses_adoption(ranged, monkeypatch):
    w, chapters, boatman, existing, old_state = ranged
    proposal = _prepare(w, chapters)
    transport(monkeypatch, GeneratedText(_reply(chapters, boatman, existing, old_state), "fake"))
    sent = _send(w, proposal)
    set_content(w, chapters[1], SECOND + "又添一句。")
    # A stale card blocks the whole selection; nothing is written.
    assert _adopt(w, sent, [0, 3], expect=409)["error"]["code"] == "TIMELINE_EXTRACTION_STALE"
    assert list(_events(w)) == [existing["id"]]
    assert _api(w, "get", f"/timeline-proposals/{sent['id']}")["adoptions"] == []
    # The first chapter is unchanged, so its event card is still adoptable.
    assert [item["index"] for item in _adopt(w, sent, [0])["adoptions"]] == [0]
    # An author edit to the state to be ended refuses the replacing state card.
    _api(
        w,
        "put",
        f"/state-intervals/{old_state['id']}",
        {
            "expected_version": 1,
            "character_id": boatman,
            "attribute": "injury",
            "label": "左臂伤势",
            "value": "作者改过",
            "start_event_id": existing["id"],
        },
    )
    assert _adopt(w, sent, [1], expect=409)["error"]["code"] == "TIMELINE_EXTRACTION_STALE"
    assert len(_states(w)) == 1


def test_cloud_send_needs_consent_and_restart_fails_running(ranged, monkeypatch):
    w, chapters, *_ = ranged
    store = w.app.state.story_control_service.timeline_service._store
    proposal = _prepare(w, chapters)
    store.mutate(
        w.project,
        proposal["id"],
        1,
        lambda current: TimelineProposal.model_validate(
            {**current.model_dump(), "status": "running", "attempts": 1}
        ),
    )
    store.recover_interrupted()
    recovered = _api(w, "get", f"/timeline-proposals/{proposal['id']}")
    assert recovered["status"] == "failed" and recovered["error"] == "AIProviderInterrupted"
    calls = transport(monkeypatch)
    cloud = _prepare(w, chapters)
    _, version = store.get(w.project, cloud["id"])
    store.mutate(
        w.project,
        cloud["id"],
        version,
        lambda current: TimelineProposal.model_validate(
            {**current.model_dump(), "model": {**current.model, "kind": "cloud"}}
        ),
    )
    refused = _send(w, {**cloud, "version": version + 1}, expect=403)
    assert refused["error"]["code"] == "TIMELINE_EXTRACTION_CONSENT_REQUIRED"
    assert calls == [] and usage(w)["items"] == []


def _frozen():
    return TimelineProposal.model_validate(
        {
            "id": "p",
            "project_id": "project",
            "status": "running",
            "attempts": 1,
            "model": {"id": "m", "kind": "local"},
            "author_request": "",
            "chapters": [
                {
                    "chapter_id": "c1",
                    "volume_id": "v1",
                    "title": "一",
                    "volume_position": 1,
                    "position": 1,
                    "revision_id": "r1",
                    "characters": 8,
                    "content": "船夫藏刀。灯灭。",
                }
            ],
            "total_characters": 8,
            "characters": [
                {"character_id": "a", "name": "船夫"},
                {"character_id": "b", "name": "少主"},
            ],
            "events": [
                {
                    "id": "e1",
                    "version": 1,
                    "title": "离岸",
                    "description": "",
                    "story_time": "",
                    "chapter_id": None,
                    "character_ids": [],
                }
            ],
            "events_omitted": 0,
            "states": [
                {
                    "id": "s1",
                    "version": 1,
                    "character_id": "a",
                    "attribute": "possession",
                    "label": "刀",
                    "value": "无",
                    "start_event_id": "e1",
                }
            ],
            "states_omitted": 0,
            "state_versions": {"s1": 1},
            "created_at": "t",
            "updated_at": "t",
        }
    )


def _state(**values):
    return {
        "kind": "state",
        "character_id": "a",
        "attribute": "possession",
        "label": "刀",
        "value": "有",
        "chapter_id": "c1",
        "quote": "船夫藏刀。",
        **values,
    }


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "not json",
        '{"summary": "x"}',
        '{"cards": [{"kind": "rewrite", "chapter_id": "c1", "quote": "灯灭"}]}',
        '{"cards": [{"kind": "event", "title": "x", "chapter_id": "c1", "quote": "灯灭",'
        ' "extra": 1}]}',
        '{"cards": [{"kind": "event", "title": "x", "chapter_id": "c1", "quote": "灯灭",'
        ' "character_ids": ["a", "a"]}]}',
        json.dumps({"cards": [_state()]}),  # No start event.
        json.dumps({"cards": [_state(start_event_id="e1", start_event_card=0)]}),
        json.dumps({"cards": [_state(start_event_id="e1", attribute="mood")]}),
        json.dumps({"cards": [_state(start_event_card=30)]}),
        json.dumps({"cards": [_state(start_event_id="e1", value=" ")]}),
    ],
)
def test_strict_output_schema_rejects_unbounded_or_unknown_replies(reply):
    with pytest.raises(TimelineOutputInvalid):
        parse_output(_frozen(), reply)


def test_quotes_and_references_are_checked_per_card():
    def event(**values):
        return {"kind": "event", "chapter_id": "c1", "quote": "灯灭。", **values}

    reply = json.dumps(
        {
            "cards": [
                _state(start_event_card=1),  # 0: starts at the valid event card below.
                event(title="灯灭", character_ids=["b"], after_event_ids=["e1"]),  # 1
                event(title="外章", chapter_id="c9"),  # 2
                event(title="无人", character_ids=["z"]),  # 3
                event(title="无前", after_event_ids=["e9"]),  # 4
                event(title="错引", quote="灯亮"),  # 5
                event(title="离岸"),  # 6: same title as a frozen event.
                event(title="灯灭"),  # 7: same title as card 1.
                _state(start_event_card=5),  # 8: starts at an invalid card.
                _state(start_event_card=0),  # 9: card 0 is not an event.
                _state(start_event_id="e9"),  # 10
                _state(start_event_id="e1", character_id="z"),  # 11
                _state(start_event_id="e1", ends_state_id="s9"),  # 12
                _state(start_event_id="e1", ends_state_id="s1", character_id="b"),  # 13
                _state(start_event_id="e1", ends_state_id="s1"),  # 14
                _state(start_event_id="e1", ends_state_id="s1"),  # 15
                _state(start_event_id="e1", quote="船夫无刀"),  # 16
                _state(start_event_card=29),  # 17: beyond the reply.
            ]
        },
        ensure_ascii=False,
    )
    output, checks = parse_output(_frozen(), reply)
    assert len(output.cards) == 18
    assert [(check.valid, check.problem) for check in checks] == [
        (True, None),
        (True, None),
        (False, "unknown_chapter"),
        (False, "unknown_character"),
        (False, "unknown_event"),
        (False, "quote_not_found"),
        (False, "duplicate_title"),
        (False, "duplicate_title"),
        (False, "unknown_event_card"),
        (False, "unknown_event_card"),
        (False, "unknown_event"),
        (False, "unknown_character"),
        (False, "unknown_state"),
        (False, "state_mismatch"),
        (True, None),
        (False, "duplicate_end"),
        (False, "quote_not_found"),
        (False, "unknown_event_card"),
    ]


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

    assert _run_alembic(path, "upgrade", "0024_add_chapter_drafts").returncode == 0
    before = triggers()
    upgraded = _run_alembic(path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    ledger = objects("SELECT sql FROM sqlite_master WHERE name='model_usage_attempts'")[0][0]
    assert "'timeline_extraction'" in ledger and "'chapter_draft'" in ledger
    assert triggers() == before and before
    assert objects("SELECT version_num FROM alembic_version") == [("0026_add_timeline_proposals",)]
    down = _run_alembic(path, "downgrade", "0024_add_chapter_drafts")
    assert down.returncode == 0, down.stderr
    assert objects("SELECT name FROM sqlite_master WHERE name='timeline_proposals'") == []
    assert triggers() == before
    assert _run_alembic(path, "upgrade", "head").returncode == 0
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO timeline_proposals (id, project_id, version, payload) "
            "VALUES ('p', 'x', 1, '{}')"
        )
        connection.commit()
    refused = _run_alembic(path, "downgrade", "0024_add_chapter_drafts")
    assert refused.returncode != 0 and "must be retained" in refused.stderr
