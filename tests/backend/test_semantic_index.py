"""C-4 semantic index over real migrated SQLite and HTTP; only the embeddings transport is a
deterministic fake (keyword-count vectors). No real or paid model is ever called."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_candidate_edits_budget import put_budget, put_price
from tests.backend.test_model_gateway import FakeProtector
from tests.backend.test_novel_structure_migration import _run_alembic
from tests.backend.test_story_control import add_chapter, api, set_content, volume_of
from tests.backend.test_story_memory import confirm, fact, provider, send
from tests.backend.test_usage_ledger import rows, usage

from aiwebnovel.ai_writing.application.models import GenerationMessage, ProviderUsage
from aiwebnovel.ai_writing.errors import (
    AIProviderInvalidResponse,
    AIProviderUnavailable,
    InvalidAIInput,
)
from aiwebnovel.model_gateway import provider as gateway_provider
from aiwebnovel.model_gateway.provider import (
    EmbeddingResult,
    embeddings_endpoint,
    parse_embeddings,
)
from aiwebnovel.model_gateway.service import ModelGatewayService
from aiwebnovel.usage.attribution import current_usage_attribution

__all__ = ["workflow"]

KEYWORDS = ("伤", "痛", "雨", "剑", "灯")
LATER = "他的手臂隐隐作痛，伤口发烫，仍要撑过今夜。"
EMBEDDING = {
    "name": "本地嵌入",
    "kind": "local",
    "base_url": "http://127.0.0.1:18124/v1",
    "model": "fake-embed",
    "max_output_tokens": 1,
    "purpose": "embedding",
}


def vector(text: str) -> tuple[float, ...]:
    """Deterministic fake embedding: keyword counts plus a small constant axis."""
    return (*(float(text.count(word)) for word in KEYWORDS), 0.05)


def embeddings(monkeypatch, *failures):
    """Replace only the outgoing embeddings HTTP call; record what would have been sent."""
    calls = []
    queue = list(failures)

    def fake(profile, texts, *, api_key):
        calls.append((profile.model, texts, current_usage_attribution()))
        if queue:
            failure = queue.pop(0)
            if failure is not None:
                raise failure
        tokens = sum(len(text) for text in texts)
        return EmbeddingResult(
            tuple(vector(text) for text in texts),
            profile.model,
            ProviderUsage(tokens, None, tokens),
        )

    monkeypatch.setattr("aiwebnovel.model_gateway.service.embed_texts", fake)
    return calls


def create_embedding_profile(w, **changes):
    response = w.client.post("/api/v1/ai/models", headers=w.headers, json={**EMBEDDING, **changes})
    assert response.status_code == 201, response.text
    assert response.json()["purpose"] == "embedding"
    return response.json()["id"]


def create_chat_profile(w):
    response = w.client.post(
        "/api/v1/ai/models",
        headers=w.headers,
        json={**EMBEDDING, "name": "对话", "purpose": "chat", "max_output_tokens": 512},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def index_path(w):
    return f"/projects/{w.project}/semantic-index"


def status(w):
    return api(w, "get", index_path(w))


def settings(w, profile, enabled=True, expect=200):
    current = status(w)["settings"]["version"]
    return api(
        w,
        "put",
        index_path(w) + "/settings",
        {"expected_version": current, "enabled": enabled, "profile_id": profile},
        expect,
    )


def build(w, plan_version=None, expect=200, **values):
    body = {
        "plan_version": plan_version or status(w)["plan"]["plan_version"],
        "confirm_estimate": True,
        **values,
    }
    return api(w, "post", index_path(w) + "/build", body, expect)


def preview(w, chapter, body=None):
    return api(w, "post", f"/chapters/{chapter}/recall-preview", body or {})


def setup_story(w):
    """Chapter 1 holds the facts; chapter 2 is the one being written."""
    later = add_chapter(w, volume_of(w), "后文", 2, LATER)
    wound = confirm(w, fact(w, title="船夫旧伤", text="船夫左臂有旧伤，阴天会痛"))
    weather = confirm(w, fact(w, title="渡口天气", text="渡口正在下雨，手臂湿透"))
    sword = confirm(w, fact(w, title="老宅秘密", text="老宅地窖藏着一把剑"))
    return later, wound, weather, sword


def entry_count(w):
    with closing(sqlite3.connect(w.db)) as connection:
        return connection.execute("SELECT COUNT(*) FROM semantic_index_entries").fetchone()[0]


# -- gateway ---------------------------------------------------------------------------


def test_embedding_profiles_are_separate_from_generation(tmp_path: Path) -> None:
    service = ModelGatewayService(tmp_path, protector=FakeProtector())
    chat = service.create_profile(
        name="对话", kind="local", base_url="http://127.0.0.1:1234/v1", model="chat"
    )
    embed = service.create_profile(
        name="嵌入",
        kind="local",
        base_url="http://127.0.0.1:1234/v1",
        model="embed",
        purpose="embedding",
    )
    stored = json.loads((tmp_path / "config/model-gateway/profiles.json").read_bytes())
    # Chat profiles keep the pre-C-4 shape; only embedding profiles record a purpose.
    assert "purpose" not in stored["profiles"][0]
    assert stored["profiles"][1]["purpose"] == "embedding"
    restarted = ModelGatewayService(tmp_path, protector=FakeProtector())
    assert [item.purpose for item in restarted.list_profiles()] == ["chat", "embedding"]
    with pytest.raises(InvalidAIInput):
        service.generate(embed.id, (GenerationMessage("user", "正文"),))
    with pytest.raises(InvalidAIInput):
        service.embed(chat.id, ("正文",))


def test_embeddings_transport_parses_ordered_vectors_and_usage(monkeypatch) -> None:
    assert embeddings_endpoint("local", "http://127.0.0.1:1234/v1").path == "/v1/embeddings"
    assert embeddings_endpoint("cloud", "https://api.example.com/v1/").path == "/v1/embeddings"
    assert parse_embeddings(
        {"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]}, 2
    ) == ((1.0, 0.0), (0.0, 1.0))
    for bad in (
        {"data": [{"embedding": [1]}]},
        {"data": [{"embedding": [1]}, {"embedding": [1, 2]}]},
        {"data": [{"embedding": ["x"]}, {"embedding": [1]}]},
        {"data": [{"index": 0, "embedding": [1]}, {"index": 0, "embedding": [1]}]},
        {"nothing": []},
    ):
        with pytest.raises(AIProviderInvalidResponse):
            parse_embeddings(bad, 2)
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = json.dumps(
        {
            "data": [{"index": 0, "embedding": [0.5, 0.5]}],
            "usage": {"prompt_tokens": 7, "total_tokens": 7},
        }
    ).encode()
    monkeypatch.setattr(
        gateway_provider.http.client, "HTTPConnection", Mock(return_value=connection)
    )
    profile = gateway_provider.ModelProfile(
        "0" * 32, "嵌入", "local", "http://127.0.0.1:1234/v1", "embed", 1, False, "embedding"
    )
    result = gateway_provider.embed_texts(profile, ("一段正文",), api_key=None)
    assert result.vectors == ((0.5, 0.5),)
    assert result.usage == ProviderUsage(7, None, 7)
    assert connection.request.call_args.args[:2] == ("POST", "/v1/embeddings")
    assert json.loads(connection.request.call_args.kwargs["body"]) == {
        "model": "embed",
        "input": ["一段正文"],
    }
    connection.close.assert_called_once()


# -- plan / estimate / confirm -----------------------------------------------------------


def test_status_estimates_without_any_model_request(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    setup_story(w)
    profile = create_embedding_profile(w)
    put_price(w, profile=profile, inp="1", out="0")
    # Enabling needs a profile, and a chat profile cannot serve as the embedding model.
    assert settings(w, None, enabled=True, expect=422)["error"]["code"] == "SEMANTIC_INDEX_INVALID"
    chat = create_chat_profile(w)
    assert settings(w, chat, expect=422)["error"]["code"] == "SEMANTIC_INDEX_INVALID"
    settings(w, profile, enabled=False)
    state = status(w)
    assert state["profile"]["id"] == profile and state["profile_problem"] is None
    assert state["facts_total"] == 3 and state["facts_indexed"] == 0
    assert state["chapters_total"] == 2 and state["chapters_indexed"] == 0
    plan = state["plan"]
    assert plan["fact_items"] == 3 and plan["chunk_items"] == 2 and plan["requests"] == 1
    estimate = state["estimate"]
    assert estimate["output_tokens_upper"] == 0
    assert estimate["input_tokens_upper"] > 0 and estimate["currency"] == "CNY"
    assert estimate["estimated_cost_upper"] is not None and estimate["decision"] == "allowed"
    assert calls == [] and w.calls == [] and usage(w)["items"] == [] and entry_count(w) == 0


def test_build_requires_confirmation_and_the_exact_reviewed_plan(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    setup_story(w)
    profile = create_embedding_profile(w)
    put_price(w, profile=profile, inp="1", out="0")
    settings(w, profile)
    reviewed = status(w)["plan"]["plan_version"]
    unconfirmed = build(w, reviewed, expect=403, confirm_estimate=False)
    assert unconfirmed["error"]["code"] == "SEMANTIC_INDEX_CONFIRMATION_REQUIRED"
    # A new price changes the shown estimate, so the reviewed plan is no longer valid.
    put_price(w, version=1, profile=profile, inp="3", out="0")
    assert build(w, reviewed, expect=409)["error"]["code"] == "SEMANTIC_INDEX_CONFLICT"
    assert calls == [] and usage(w)["items"] == [] and entry_count(w) == 0


def test_cloud_embedding_needs_explicit_cloud_consent(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    setup_story(w)
    service = w.app.state.model_gateway_service
    monkeypatch.setattr(service, "_protector", FakeProtector())
    profile = service.create_profile(
        name="云嵌入",
        kind="cloud",
        base_url="https://api.example.com/v1",
        model="cloud-embed",
        api_key="test-key-not-real",
        purpose="embedding",
    ).id
    settings(w, profile)
    refused = build(w, expect=403)
    assert refused["error"]["code"] == "SEMANTIC_INDEX_CONFIRMATION_REQUIRED"
    assert calls == []
    result = build(w, cloud_consent=True)
    assert result["requests_sent"] == 1 and len(calls) == 1


# -- metering / budget -----------------------------------------------------------------


def test_build_meters_every_request_as_semantic_index(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    later, *_ = setup_story(w)
    profile = create_embedding_profile(w)
    put_price(w, profile=profile, inp="1", out="0")
    settings(w, profile)
    result = build(w)
    assert result["requests_sent"] == 1 and result["items_indexed"] == 5
    assert len(calls) == 1
    assert calls[0][2].operation == "semantic_index"
    assert calls[0][2].task_id == result["build_id"]
    assert LATER in calls[0][1]
    ledger = usage(w)["items"]
    assert [(row["operation"], row["task_id"], row["status"]) for row in ledger] == [
        ("semantic_index", result["build_id"], "completed")
    ]
    assert ledger[0]["reported_input_tokens"] == sum(len(text) for text in calls[0][1])
    assert ledger[0]["model_name"] == "fake-embed" and ledger[0]["output_characters"] == 0
    assert usage(w)["by_operation"][0]["operation"] == "semantic_index"
    state = result["status"]
    assert state["up_to_date"] and state["plan"] is None and state["estimate"] is None
    assert state["facts_indexed"] == 3 and state["chapters_indexed"] == 2
    assert entry_count(w) == 5
    # Reads and recall never call the model again; a second build has nothing to do.
    preview(w, later)
    assert len(calls) == 1
    again = api(
        w,
        "post",
        index_path(w) + "/build",
        {"plan_version": "0" * 64, "confirm_estimate": True},
        409,
    )
    assert again["error"]["code"] == "SEMANTIC_INDEX_UP_TO_DATE"
    assert len(rows(w)) == 1


def test_strict_budget_refuses_the_whole_build_before_sending(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    setup_story(w)
    profile = create_embedding_profile(w)
    put_price(w, profile=profile, inp="100000", out="0")
    put_budget(w, task_limit="0.01")
    settings(w, profile)
    state = status(w)
    assert state["estimate"]["decision"] == "refused"
    assert "TASK_LIMIT_EXCEEDED" in state["estimate"]["reasons"]
    refused = build(w, state["plan"]["plan_version"], expect=409)
    assert refused["error"]["code"] == "AI_BUDGET_REFUSED"
    assert calls == [] and rows(w) == [] and entry_count(w) == 0


def test_unpriced_embedding_profile_is_refused_by_a_strict_budget(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    setup_story(w)
    profile = create_embedding_profile(w)
    put_budget(w, task_limit="5")
    settings(w, profile)
    state = status(w)
    assert state["estimate"]["decision"] == "refused"
    assert "PRICE_MISSING" in state["estimate"]["reasons"]
    assert build(w, expect=409)["error"]["code"] == "AI_BUDGET_REFUSED"
    assert calls == [] and rows(w) == []


def test_failed_request_keeps_earlier_batches_and_records_the_failure(workflow, monkeypatch):
    w = workflow
    setup_story(w)
    for index in range(40):  # enough facts for two requests (32 inputs per request)
        confirm(w, fact(w, title=f"事实{index}", text=f"第{index}条已确认的灯下细节"))
    profile = create_embedding_profile(w)
    settings(w, profile)
    plan = status(w)["plan"]
    assert plan["requests"] == 2
    calls = embeddings(monkeypatch, None, AIProviderUnavailable())
    failed = build(w, plan["plan_version"], expect=502)
    assert failed["error"]["code"] == "AI_PROVIDER_UNAVAILABLE"
    assert len(calls) == 2
    assert [row["status"] for row in rows(w)] == ["completed", "failed"]
    state = status(w)
    assert entry_count(w) == 32 and not state["up_to_date"]
    assert state["plan"]["fact_items"] + state["plan"]["chunk_items"] == 45 - 32
    assert state["plan"]["requests"] == 1  # nothing is resent automatically


# -- incremental -----------------------------------------------------------------------


def test_incremental_update_sends_only_changed_or_new_items(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    later, wound, weather, _ = setup_story(w)
    profile = create_embedding_profile(w)
    settings(w, profile)
    build(w)
    assert len(calls) == 1
    # One new confirmed fact, one fact edited (new revision), one chapter rewritten.
    added = confirm(w, fact(w, title="灯塔", text="港口的灯塔熄灭了"))
    confirm(w, weather, text="渡口雨停了，手臂仍湿")
    set_content(w, later, LATER + "灯火摇晃。")
    state = status(w)
    assert state["stale_entries"] == 2  # the edited fact and the rewritten chapter chunk
    assert state["plan"]["fact_items"] == 2 and state["plan"]["chunk_items"] == 1
    result = build(w)
    sent = calls[1][1]
    assert len(calls) == 2 and len(sent) == 3
    assert "灯塔\n港口的灯塔熄灭了" in sent and LATER + "灯火摇晃。" in sent
    assert all(wound["text"] not in text for text in sent)
    assert result["status"]["up_to_date"] and entry_count(w) == 6
    assert added["id"]


# -- recall ----------------------------------------------------------------------------


def test_semantic_recall_mixes_similarity_and_falls_back_when_stale(workflow, monkeypatch):
    w = workflow
    embeddings(monkeypatch)
    later, wound, weather, sword = setup_story(w)
    deterministic = preview(w, later)
    assert deterministic["mode"] == "deterministic" and deterministic["semantic_note"] is None
    # "手臂" is the only literal overlap, so deterministic recall ranks the weather first.
    assert deterministic["selected"][0]["id"] == weather["id"]

    profile = create_embedding_profile(w)
    settings(w, profile)
    missing = preview(w, later)
    assert missing["mode"] == "fallback" and "尚未建立语义索引" in missing["semantic_note"]
    assert [item["id"] for item in missing["selected"]] == [
        item["id"] for item in deterministic["selected"]
    ]

    build(w)
    semantic = preview(w, later)
    assert semantic["mode"] == "semantic" and semantic["semantic_note"] is None
    order = [item["id"] for item in semantic["selected"]]
    # The wound (伤/痛) is semantically closest; the overlap still lifts the weather above
    # the unrelated sword.
    assert order == [wound["id"], weather["id"], sword["id"]]
    similarity = {item["id"]: item["similarity"] for item in semantic["selected"]}
    assert similarity[wound["id"]] > similarity[weather["id"]] >= similarity[sword["id"]]

    # Author pins and exclusions still come first in semantic mode.
    pinned = preview(
        w, later, {"pinned_fact_ids": [sword["id"]], "excluded_fact_ids": [wound["id"]]}
    )
    assert pinned["mode"] == "semantic"
    assert [(item["id"], item["reason"]) for item in pinned["selected"]] == [
        (sword["id"], "pinned"),
        (weather["id"], "related"),
    ]

    # Generation's "本次依据" and the review snapshot record the semantic order.
    run = api(w, "post", f"/chapters/{later}/ai/runs", {"profile_id": "default-local"}, 201)
    memory = next(
        item for item in run["context"]["manifest"]["sources"] if item["source"] == "story_memory"
    )
    assert "语义相似度" in memory["reason"]
    assert [item[0] for item in memory["references"]] == order
    calls = provider(w)
    revision = w.client.get(f"/api/v1/chapters/{later}/content").json()["current_revision_id"]
    review = api(
        w,
        "post",
        f"/chapters/{later}/memory/reviews",
        {"source_revision": revision, "profile_id": "default-local"},
        201,
    )
    assert review["recall"]["mode"] == "semantic"
    assert [item["id"] for item in review["facts"]] == order
    assert review["recall"]["selected"][0]["similarity"] == pytest.approx(
        similarity[wound["id"]], abs=1e-5
    )
    assert send(w, review).status_code == 200 and len(calls) == 1

    # Editing the chapter makes its index stale: recall falls back and says so.
    set_content(w, later, LATER + "雨又下了起来。")
    stale = preview(w, later)
    assert stale["mode"] == "fallback" and "已修改" in stale["semantic_note"]
    run = api(w, "post", f"/chapters/{later}/ai/runs", {"profile_id": "default-local"}, 201)
    memory = next(
        item for item in run["context"]["manifest"]["sources"] if item["source"] == "story_memory"
    )
    assert "语义召回不可用" in memory["reason"]
    # The earlier review keeps its frozen semantic explanation.
    frozen = next(
        item
        for item in api(w, "get", f"/chapters/{later}/memory")["reviews"]
        if item["id"] == review["id"]
    )
    assert frozen["recall"]["mode"] == "semantic"


def test_new_unindexed_fact_falls_back_instead_of_partial_ranking(workflow, monkeypatch):
    w = workflow
    embeddings(monkeypatch)
    later, *_ = setup_story(w)
    profile = create_embedding_profile(w)
    settings(w, profile)
    build(w)
    assert preview(w, later)["mode"] == "semantic"
    confirm(w, fact(w, title="新事实", text="新确认的事实"))
    stale = preview(w, later)
    assert stale["mode"] == "fallback" and "1 项可召回事实" in stale["semantic_note"]
    # Disabling semantic recall returns to plain deterministic recall without a note.
    settings(w, profile, enabled=False)
    plain = preview(w, later)
    assert plain["mode"] == "deterministic" and plain["semantic_note"] is None


def test_changing_the_embedding_model_invalidates_every_vector(workflow, monkeypatch):
    w = workflow
    calls = embeddings(monkeypatch)
    later, *_ = setup_story(w)
    profile = create_embedding_profile(w)
    settings(w, profile)
    build(w)
    response = w.client.put(
        f"/api/v1/ai/models/{profile}",
        headers=w.headers,
        json={**EMBEDDING, "model": "fake-embed-v2"},
    )
    assert response.status_code == 200, response.text
    assert preview(w, later)["mode"] == "fallback"
    state = status(w)
    assert state["facts_indexed"] == 0 and state["stale_entries"] == 5
    assert state["plan"]["fact_items"] == 3 and state["plan"]["chunk_items"] == 2
    build(w)
    assert calls[-1][0] == "fake-embed-v2" and preview(w, later)["mode"] == "semantic"


# -- migration -------------------------------------------------------------------------


def test_migration_adds_tables_and_ledger_operation_and_keeps_records(tmp_path):
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
    upgraded = _run_alembic(path, "upgrade", "0025_add_semantic_index")
    assert upgraded.returncode == 0, upgraded.stderr
    ledger = objects("SELECT sql FROM sqlite_master WHERE name='model_usage_attempts'")[0][0]
    assert "'semantic_index'" in ledger and "'chapter_draft'" in ledger
    assert triggers() == before and before
    assert objects("SELECT version_num FROM alembic_version") == [("0025_add_semantic_index",)]
    down = _run_alembic(path, "downgrade", "0024_add_chapter_drafts")
    assert down.returncode == 0, down.stderr
    assert objects("SELECT name FROM sqlite_master WHERE name LIKE 'semantic_index%'") == []
    assert triggers() == before
    assert _run_alembic(path, "upgrade", "0025_add_semantic_index").returncode == 0
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO semantic_index_settings (id, project_id, version, enabled, profile_id,"
            " created_at) VALUES ('s', 'x', 1, 0, NULL, 't')"
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE semantic_index_settings SET enabled = 1")
    refused = _run_alembic(path, "downgrade", "0024_add_chapter_drafts")
    assert refused.returncode != 0 and "must be retained" in refused.stderr
