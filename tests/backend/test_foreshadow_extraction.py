"""C-2 batch foreshadow extraction over real migrated SQLite and HTTP; only the transport is fake."""

import json
import sqlite3
from contextlib import closing

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_candidate_edits_budget import put_budget
from tests.backend.test_story_control import add_chapter, set_content, volume_of
from tests.backend.test_usage_ledger import transport, usage

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.story_control.foreshadow import parse_output
from aiwebnovel.story_control.foreshadow_models import (
    MAX_TOTAL_CHARACTERS,
    ForeshadowOutputInvalid,
    ForeshadowProposal,
)

__all__ = ["workflow"]

FIRST = "雨😀雨。船夫左臂缠着旧布，从不在人前解开。"
SECOND = "夜里渡口起火。船夫解开旧布，露出一道刀疤，那是当年替少主挡下的一刀。"


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


def _threads(w):
    timeline = _api(w, "get", "/timeline")
    return {view["thread"]["id"]: view["thread"] for view in timeline["threads"]}


def _prepare(w, chapters, expect=201, **values):
    body = {"chapter_ids": chapters, "profile_id": "default-local", **values}
    return _api(w, "post", "/foreshadow-proposals", body, expect)


def _send(w, proposal, expect=200, **values):
    body = {"expected_version": proposal["version"], "cloud_consent": False, **values}
    return _api(w, "post", f"/foreshadow-proposals/{proposal['id']}/send", body, expect)


def _adopt(w, proposal, indexes, expect=200):
    body = {"card_indexes": indexes}
    return _api(w, "post", f"/foreshadow-proposals/{proposal['id']}/adopt", body, expect)


def _count(w, table):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.fixture
def ranged(workflow):
    w = workflow
    set_content(w, w.chapter, FIRST)
    volume = volume_of(w)
    second = add_chapter(w, volume, "第二章", 2, SECOND)
    existing = _api(
        w,
        "post",
        "/plot-threads",
        {"expected_version": 0, "title": "少主身世", "content": "少主不是亲生"},
        201,
    )
    return w, [w.chapter, second], existing


def _reply(chapters, thread_id, *, bad_quote=False):
    return json.dumps(
        {
            "summary": "两章里有一处新伏笔、一处兑现",
            "cards": [
                {
                    "kind": "new_thread",
                    "title": "船夫的旧伤",
                    "content": "左臂旧布下藏着往事",
                    "chapter_id": chapters[0],
                    "quote": "船夫左臂缠着旧布，从不在人前解开。",
                    "reason": "刻意遮掩",
                },
                {
                    "kind": "payoff",
                    "thread_id": thread_id,
                    "chapter_id": chapters[1],
                    "quote": "那是当年替少主挡下的一刀。",
                },
                {
                    "kind": "new_thread",
                    "title": "渡口火因",
                    "chapter_id": chapters[1],
                    "quote": "渡口起火的真相是纵火" if bad_quote else "夜里渡口起火。",
                },
            ],
        },
        ensure_ascii=False,
    )


def test_preview_and_prepare_freeze_range_without_any_model_request(ranged, monkeypatch):
    w, chapters, existing = ranged
    calls = transport(monkeypatch)
    preview = _api(w, "post", "/foreshadow-proposals/preview", {"chapter_ids": chapters[::-1]})
    assert [item["chapter_id"] for item in preview["chapters"]] == chapters  # Book order.
    assert [item["characters"] for item in preview["chapters"]] == [len(FIRST), len(SECOND)]
    assert preview["total_characters"] == len(FIRST) + len(SECOND)
    assert preview["max_chapters"] == 10 and preview["problem"] is None
    assert preview["open_threads"] == 1
    proposal = _prepare(w, chapters, author_request="只看人物伏笔")
    assert proposal["status"] == "ready" and proposal["version"] == 1
    assert [item["characters"] for item in proposal["chapters"]] == [len(FIRST), len(SECOND)]
    assert "content" not in proposal["chapters"][0]
    assert [item["id"] for item in proposal["threads"]] == [existing["id"]]
    assert FIRST in proposal["request_preview"] and "只看人物伏笔" in proposal["request_preview"]
    estimate = _api(w, "get", f"/foreshadow-proposals/{proposal['id']}/estimate")
    assert estimate["decision"] == "allowed" and estimate["input_characters"] > len(FIRST)
    listed = _api(w, "get", "/foreshadow-proposals")
    assert [item["id"] for item in listed["items"]] == [proposal["id"]]
    assert listed["items"][0]["chapter_ids"] == chapters
    assert calls == [] and usage(w)["items"] == []


def test_range_bounds_are_refused_before_anything_is_stored(ranged, monkeypatch):
    w, chapters, _ = ranged
    calls = transport(monkeypatch)
    volume = volume_of(w)
    empty = add_chapter(w, volume, "空章", 3)
    preview = _api(w, "post", "/foreshadow-proposals/preview", {"chapter_ids": [empty]})
    assert preview["problem"] == "empty_chapter"
    assert _prepare(w, [empty], expect=422)["error"]["code"] == "FORESHADOW_EXTRACTION_INVALID"
    big = add_chapter(w, volume, "长章", 4, "长" * (MAX_TOTAL_CHARACTERS - len(FIRST) + 1))
    preview = _api(w, "post", "/foreshadow-proposals/preview", {"chapter_ids": [chapters[0], big]})
    assert preview["problem"] == "too_many_characters"
    assert _prepare(w, [chapters[0], big], expect=422)["error"]["code"] == (
        "FORESHADOW_EXTRACTION_INVALID"
    )
    assert _prepare(w, ["missing"], expect=422)["error"]["code"] == (
        "FORESHADOW_EXTRACTION_INVALID"
    )
    eleven = [f"c{i}" for i in range(11)]
    assert _prepare(w, eleven, expect=422)
    assert _prepare(w, [chapters[0], chapters[0]], expect=422)
    assert calls == [] and _count(w, "foreshadow_proposals") == 0


def test_strict_budget_refuses_send_without_network_or_ledger(ranged, monkeypatch):
    w, chapters, _ = ranged
    proposal = _prepare(w, chapters)
    put_budget(w, task_limit="1")
    calls = transport(monkeypatch)
    estimate = _api(w, "get", f"/foreshadow-proposals/{proposal['id']}/estimate")
    assert estimate["decision"] == "refused"
    blocked = _send(w, proposal, expect=409)
    assert blocked["error"]["code"] == "AI_BUDGET_REFUSED"
    reloaded = _api(w, "get", f"/foreshadow-proposals/{proposal['id']}")
    assert reloaded["status"] == "ready" and reloaded["attempts"] == 0
    assert calls == [] and usage(w)["items"] == []
    assert _count(w, "model_budget_reservations") == 0


def test_valid_reply_becomes_checked_cards_and_only_adopted_cards_write(ranged, monkeypatch):
    w, chapters, existing = ranged
    proposal = _prepare(w, chapters)
    reply = _reply(chapters, existing["id"], bad_quote=True)
    calls = transport(monkeypatch, GeneratedText(reply, "fake"))
    sent = _send(w, proposal)
    assert len(calls) == 1
    assert calls[0][2].operation == "foreshadow_extraction"
    assert calls[0][2].task_id == proposal["id"]
    assert sent["status"] == "completed"
    assert [card["kind"] for card in sent["cards"]] == ["new_thread", "payoff", "new_thread"]
    assert [check["valid"] for check in sent["checks"]] == [True, True, False]
    assert sent["checks"][2]["problem"] == "quote_not_found"
    rows = usage(w)["items"]
    assert [(row["operation"], row["task_id"]) for row in rows] == [
        ("foreshadow_extraction", proposal["id"])
    ]
    # Suggestions alone change no thread and no chapter.
    assert list(_threads(w)) == [existing["id"]]
    assert _send(w, sent, expect=409)["error"]["code"] == "FORESHADOW_EXTRACTION_CONFLICT"
    # A card whose quote is not in the frozen text can never be adopted.
    refused = _adopt(w, sent, [0, 2], expect=422)
    assert refused["error"]["code"] == "FORESHADOW_CARD_INVALID"
    assert list(_threads(w)) == [existing["id"]]

    adopted = _adopt(w, sent, [0])
    assert [(item["index"], item["action"]) for item in adopted["adoptions"]] == [(0, "created")]
    threads = _threads(w)
    created = threads[adopted["adoptions"][0]["thread_id"]]
    assert created["status"] == "planted" and created["title"] == "船夫的旧伤"
    assert created["planned_setup_chapter_id"] == chapters[0]
    assert created["anchors"][0]["quote"] == "船夫左臂缠着旧布，从不在人前解开。"
    assert threads[existing["id"]]["version"] == 1  # Unselected payoff card untouched.

    # Adopting again never duplicates; a new subset adds only the new card.
    again = _adopt(w, adopted, [0])
    assert again["adoptions"] == adopted["adoptions"]
    later = _adopt(w, adopted, [1, 0])
    assert [(item["index"], item["action"]) for item in later["adoptions"]] == [
        (0, "created"),
        (1, "paid_off"),
    ]
    threads = _threads(w)
    assert len(threads) == 2
    paid = threads[existing["id"]]
    assert paid["status"] == "paid_off" and paid["version"] == 2
    assert [(a["role"], a["chapter_id"]) for a in paid["anchors"]] == [("payoff", chapters[1])]
    assert _adopt(w, later, [1])["adoptions"] == later["adoptions"]
    assert _threads(w)[existing["id"]]["version"] == 2
    assert len(calls) == 1
    assert _adopt(w, later, [7], expect=422)["error"]["code"] == "FORESHADOW_EXTRACTION_INVALID"


def test_invalid_reply_fails_with_evidence_and_no_retry(ranged, monkeypatch):
    w, chapters, existing = ranged
    proposal = _prepare(w, chapters)
    raw = "好的，以下是伏笔 ```json {}```"
    calls = transport(monkeypatch, GeneratedText(raw, "fake"))
    failed = _send(w, proposal)
    assert failed["status"] == "failed" and failed["error"] == "ForeshadowOutputInvalid"
    assert failed["evidence"] == raw and failed["cards"] == []
    assert len(calls) == 1 and len(usage(w)["items"]) == 1
    assert _send(w, failed, expect=409)["error"]["code"] == "FORESHADOW_EXTRACTION_CONFLICT"
    assert _adopt(w, failed, [0], expect=409)["error"]["code"] == ("FORESHADOW_EXTRACTION_CONFLICT")
    assert len(calls) == 1 and list(_threads(w)) == [existing["id"]]


def test_changed_chapter_text_or_thread_refuses_adoption(ranged, monkeypatch):
    w, chapters, existing = ranged
    proposal = _prepare(w, chapters)
    transport(monkeypatch, GeneratedText(_reply(chapters, existing["id"]), "fake"))
    sent = _send(w, proposal)
    set_content(w, chapters[0], FIRST + "又添一句。")
    stale = _adopt(w, sent, [0], expect=409)
    assert stale["error"]["code"] == "FORESHADOW_EXTRACTION_STALE"
    # A stale card in the selection blocks the whole selection; nothing is written.
    assert _adopt(w, sent, [2, 0], expect=409)["error"]["code"] == "FORESHADOW_EXTRACTION_STALE"
    assert list(_threads(w)) == [existing["id"]]
    assert _api(w, "get", f"/foreshadow-proposals/{sent['id']}")["adoptions"] == []
    # The second chapter is unchanged, so its card is still adoptable.
    assert [item["index"] for item in _adopt(w, sent, [2])["adoptions"]] == [2]
    # An author edit to the thread after preparation refuses its payoff card.
    _api(
        w,
        "put",
        f"/plot-threads/{existing['id']}",
        {"expected_version": 1, "title": "少主身世", "content": "作者改过"},
    )
    assert _adopt(w, sent, [1], expect=409)["error"]["code"] == "FORESHADOW_EXTRACTION_STALE"
    assert _threads(w)[existing["id"]]["status"] == "planned"


def test_cloud_send_needs_consent_and_restart_fails_running(ranged, monkeypatch):
    w, chapters, _ = ranged
    service = w.app.state.story_control_service.foreshadow_service
    store = service._store
    proposal = _prepare(w, chapters)
    store.mutate(
        w.project,
        proposal["id"],
        1,
        lambda current: ForeshadowProposal.model_validate(
            {**current.model_dump(), "status": "running", "attempts": 1}
        ),
    )
    store.recover_interrupted()
    recovered = _api(w, "get", f"/foreshadow-proposals/{proposal['id']}")
    assert recovered["status"] == "failed" and recovered["error"] == "AIProviderInterrupted"
    calls = transport(monkeypatch)
    cloud = _prepare(w, chapters)
    stored, version = store.get(w.project, cloud["id"])
    store.mutate(
        w.project,
        cloud["id"],
        version,
        lambda current: ForeshadowProposal.model_validate(
            {**current.model_dump(), "model": {**current.model, "kind": "cloud"}}
        ),
    )
    refused = _send(w, {**cloud, "version": version + 1}, expect=403)
    assert refused["error"]["code"] == "FORESHADOW_EXTRACTION_CONSENT_REQUIRED"
    assert calls == [] and usage(w)["items"] == [] and stored.status == "ready"


def _frozen():
    return ForeshadowProposal.model_validate(
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
                    "characters": 6,
                    "content": "船夫藏刀。灯灭。",
                }
            ],
            "total_characters": 8,
            "threads": [
                {
                    "id": "t1",
                    "version": 1,
                    "title": "旧刀",
                    "content": "",
                    "status": "planted",
                    "setup_chapter_ids": [],
                }
            ],
            "threads_omitted": 0,
            "thread_versions": {"t1": 1},
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
        '{"cards": [{"kind": "rewrite", "chapter_id": "c1", "quote": "灯灭"}]}',
        '{"cards": [{"kind": "new_thread", "title": "x", "chapter_id": "c1", "quote": "灯灭",'
        ' "extra": 1}]}',
        '{"cards": [{"kind": "new_thread", "title": "x", "chapter_id": "c1", "quote": ""}]}',
        '{"cards": [{"kind": "new_thread", "title": "x", "chapter_id": "c1", "quote": "'
        + "长" * 301
        + '"}]}',
        '{"cards": [{"kind": "payoff", "chapter_id": "c1", "quote": "灯灭"}]}',
        json.dumps(
            {
                "cards": [
                    {"kind": "new_thread", "title": f"t{i}", "chapter_id": "c1", "quote": "灯灭"}
                    for i in range(31)
                ]
            }
        ),
        '{"cards": [{"kind": "new_thread", "title": "x\\u0000", "chapter_id": "c1",'
        ' "quote": "灯灭"}]}',
    ],
)
def test_strict_output_schema_rejects_unbounded_or_unknown_replies(reply):
    with pytest.raises(ForeshadowOutputInvalid):
        parse_output(_frozen(), reply)


def test_quotes_and_references_are_checked_per_card():
    reply = json.dumps(
        {
            "cards": [
                {"kind": "new_thread", "title": "藏刀", "chapter_id": "c1", "quote": "船夫藏刀。"},
                {"kind": "new_thread", "title": "灯", "chapter_id": "c1", "quote": "灯亮"},
                {"kind": "new_thread", "title": "外章", "chapter_id": "c9", "quote": "灯灭"},
                {"kind": "payoff", "thread_id": "t9", "chapter_id": "c1", "quote": "灯灭"},
                {"kind": "payoff", "thread_id": "t1", "chapter_id": "c1", "quote": "灯灭"},
                {"kind": "payoff", "thread_id": "t1", "chapter_id": "c1", "quote": "灯灭"},
                {"kind": "new_thread", "title": "旧刀", "chapter_id": "c1", "quote": "灯灭"},
            ]
        },
        ensure_ascii=False,
    )
    output, checks = parse_output(_frozen(), reply)
    assert len(output.cards) == 7
    assert [(check.valid, check.problem) for check in checks] == [
        (True, None),
        (False, "quote_not_found"),
        (False, "unknown_chapter"),
        (False, "unknown_thread"),
        (True, None),
        (False, "duplicate_payoff"),
        (False, "duplicate_title"),
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

    assert _run_alembic(path, "upgrade", "0022_add_plan_proposals").returncode == 0
    before = triggers()
    upgraded = _run_alembic(path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    ledger = objects("SELECT sql FROM sqlite_master WHERE name='model_usage_attempts'")[0][0]
    assert "'foreshadow_extraction'" in ledger and "'plan_proposal'" in ledger
    assert triggers() == before and before
    assert objects("SELECT version_num FROM alembic_version") == [
        ("0023_add_foreshadow_proposals",)
    ]
    down = _run_alembic(path, "downgrade", "0022_add_plan_proposals")
    assert down.returncode == 0, down.stderr
    assert objects("SELECT name FROM sqlite_master WHERE name='foreshadow_proposals'") == []
    assert triggers() == before
    assert _run_alembic(path, "upgrade", "head").returncode == 0
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "INSERT INTO foreshadow_proposals (id, project_id, version, payload) "
            "VALUES ('p', 'x', 1, '{}')"
        )
        connection.commit()
    refused = _run_alembic(path, "downgrade", "0022_add_plan_proposals")
    assert refused.returncode != 0 and "must be retained" in refused.stderr
