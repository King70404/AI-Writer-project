"""Author plans survive reload, guard stale updates, and freeze selected source revisions."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tests.backend.factories import create_test_app
from tests.backend.test_ai_workflow import workflow

from aiwebnovel.ai_writing.application.models import ContextSource
from aiwebnovel.ai_writing.errors import AIContextChanged
from aiwebnovel.chapter_planning.models import (
    ChapterPlan,
    PlanningConflict,
    PlanningReferenceInvalid,
    SaveChapterPlan,
)
from aiwebnovel.chapter_planning.service import ChapterPlanningService

__all__ = ["workflow"]


def document(**changes):
    return {
        "expected_version": 0,
        "memory_focuses": ["主角第一次拒绝不公的交易", "失踪者留下的船票"],
        "target_characters": 3200,
        "chapter_goal": "把一次盘问推进为主动寻找失踪者的决定",
        "conflict": "想得到证据却不敢惊动船主",
        "continuity_notes": "承接上一章的伤势。结尾只揭示船票，不提前揭露幕后者。",
        "scenes": [
            {
                "id": "quay",
                "title": "渡口盘问",
                "setting": "灯光扫过潮湿木板，渡船仍在装货",
                "character_ids": [],
                "beats": [
                    {"id": "ask", "action": "以搬运货物为由打听失踪者", "change": "船夫戒备"},
                    {"id": "ticket", "action": "发现货箱下的船票", "change": "决定登船寻找"},
                ],
            }
        ],
        "include_story_bible": False,
        "writing_rule_revision_ids": [],
        **changes,
    }


def saved_document(**changes):
    values = document()
    values.pop("expected_version")
    return ChapterPlan(
        **{
            **values,
            "chapter_id": "chapter",
            "project_id": "project",
            "version": 1,
            "revision_id": "revision",
            "updated_at": "2026-10-11T00:00:00+00:00",
            **changes,
        }
    )


def save(w, **changes):
    response = w.client.put(w.base + "/planning", headers=w.headers, json=document(**changes))
    assert response.status_code == 200, response.text
    return response.json()


def test_plan_persists_reordered_scenes_beats_without_modifying_prose(workflow):
    w = workflow
    url = w.base + "/planning"
    assert w.client.get(url).json() is None
    before = w.client.get(w.base + "/content").json()
    first = save(w)
    assert first["version"] == 1
    assert first["chapter_id"] == w.chapter
    assert w.client.get(url).json() == first
    second_scene = {**document()["scenes"][0], "id": "cabin", "title": "船舱对峙"}
    second_scene["beats"] = list(reversed(second_scene["beats"]))
    second = save(w, expected_version=1, scenes=[second_scene, *document()["scenes"]])
    assert second["version"] == 2
    assert second["revision_id"] != first["revision_id"]
    assert [scene["id"] for scene in second["scenes"]] == ["cabin", "quay"]
    assert [beat["id"] for beat in second["scenes"][0]["beats"]] == ["ticket", "ask"]
    assert w.client.get(w.base + "/content").json() == before
    assert w.app.state.chapter_planning_service.get(w.chapter).model_dump() == second
    with closing(sqlite3.connect(w.db)) as connection:
        rows = connection.execute(
            "SELECT version, payload FROM chapter_plan_revisions ORDER BY version"
        ).fetchall()
        assert len(rows) == 2
        assert "cabin" not in rows[0][1] and "cabin" in rows[1][1]
        for operation in (
            "UPDATE chapter_plan_revisions SET version=8",
            "DELETE FROM chapter_plan_revisions",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(operation)


def test_plan_stale_and_concurrent_edits_do_not_overwrite(workflow):
    w = workflow
    save(w)
    conflict = w.client.put(w.base + "/planning", headers=w.headers, json=document())
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PLANNING_CONFLICT"

    def attempt(index):
        try:
            return w.app.state.chapter_planning_service.save(
                w.chapter, SaveChapterPlan(**document(expected_version=1, chapter_goal=str(index)))
            ).version
        except PlanningConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))
    assert sorted(map(str, outcomes)) == ["2", "conflict"]


def test_plan_and_frozen_preparation_survive_application_restart(workflow):
    w = workflow
    saved = save(w)
    prepared = w.client.post(w.base + "/ai/runs", headers=w.headers, json={})
    assert prepared.status_code == 201
    run = prepared.json()
    prose = w.client.get(w.base + "/content").json()
    w.app.state.ai_workflow_runtime.close()
    with TestClient(create_test_app(**w.settings)) as restarted:
        assert restarted.get(w.base + "/planning").json() == saved
        assert restarted.get(w.base + "/content").json() == prose
        assert restarted.get(w.base + "/ai/runs/" + run["run_id"]).json() == run
    assert w.calls == []


def test_plan_missing_wrong_project_assets_and_deleted_project_hidden(workflow):
    w = workflow
    other = w.client.post("/api/v1/projects", headers=w.headers, json={"title": "别的小说"})
    foreign = w.client.post(
        f"/api/v1/projects/{other.json()['project_id']}/characters",
        headers=w.headers,
        json={"name": "别书人物", "role": "", "profile": "不应发送"},
    ).json()["character_id"]
    scene = {**document()["scenes"][0], "character_ids": [foreign]}
    for changes in (
        {"scenes": [scene]},
        {"include_story_bible": True},
        {"writing_rule_revision_ids": ["missing"]},
        {"scenes": [{**scene, "character_ids": ["invalid"]}]},
    ):
        response = w.client.put(w.base + "/planning", headers=w.headers, json=document(**changes))
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "PLANNING_REFERENCE_INVALID"
    save(w)
    project_url = f"/api/v1/projects/{w.project}"
    deleted = w.client.post(
        project_url + "/delete",
        headers={**w.headers, "If-Match": w.client.get(project_url).headers["etag"]},
    )
    assert deleted.status_code == 200
    assert w.client.get(w.base + "/planning").status_code == 404
    assert w.client.put(w.base + "/planning", headers=w.headers, json=document()).status_code == 404


def test_asset_revision_context_is_frozen_at_preparation(workflow):
    w = workflow
    character = w.client.post(
        f"/api/v1/projects/{w.project}/characters",
        headers=w.headers,
        json={"name": "船夫", "role": "证人", "profile": "隐瞒货单"},
    )
    bible = w.client.post(
        f"/api/v1/projects/{w.project}/story-bible",
        headers=w.headers,
        json={"title": "港口", "content": "夜禁之后不能离港"},
    ).json()
    scene = {**document()["scenes"][0], "character_ids": [character.json()["character_id"]]}
    plan = save(w, scenes=[scene], include_story_bible=True)
    service = w.app.state.chapter_planning_service
    sources = service.context_sources(w.chapter)
    assert sources[0].references == ((w.chapter, plan["revision_id"]),)
    assert sources[1].references[0][1] == character.json()["current_revision_id"]
    assert sources[2].references[0][1] == bible["current_revision_id"]
    prepared = w.client.post(w.base + "/ai/runs", headers=w.headers, json={}).json()
    assert "隐瞒货单" in prepared["context"]["text"]
    assert "3200" in prepared["context"]["text"]
    assert w.calls == []
    update = w.client.put(
        f"/api/v1/characters/{character.json()['character_id']}",
        headers={**w.headers, "If-Match": character.headers["etag"]},
        json={"name": "船夫", "role": "证人", "profile": "作者已更新的事实"},
    )
    assert update.status_code == 200
    save(w, expected_version=1, target_characters=4500)
    reread = w.client.get(w.base + "/ai/runs/" + prepared["run_id"]).json()
    assert reread["context"] == prepared["context"]


@pytest.mark.parametrize(
    "changes",
    [
        {"memory_focuses": []},
        {"memory_focuses": [" "]},
        {"memory_focuses": ["a", "b", "c", "d"]},
        {"memory_focuses": ["a", "a"]},
        {"expected_version": True},
        {"expected_version": -1},
        {"target_characters": 199},
        {"target_characters": 20001},
        {"target_characters": "3000"},
        {"chapter_goal": "bad\x00"},
        {"conflict": "\ud800"},
        {"writing_rule_revision_ids": ["repeat", "repeat"]},
        {"writing_rule_revision_ids": [str(i) for i in range(9)]},
        {"writing_rule_revision_ids": ["bad/id"]},
        {"scenes": [{**document()["scenes"][0], "id": "bad/id"}]},
        {"scenes": [{**document()["scenes"][0], "id": " space "}]},
        {"scenes": [document()["scenes"][0]] * 2},
        {"unknown": True},
        {
            "scenes": [
                {**document()["scenes"][0], "beats": [document()["scenes"][0]["beats"][0]] * 2}
            ]
        },
        {"scenes": [{**document()["scenes"][0], "character_ids": ["a", "a"]}]},
    ],
)
def test_invalid_planning_documents_rejected(changes):
    with pytest.raises(ValidationError):
        SaveChapterPlan(**document(**changes))


def test_aggregate_size_rejected():
    scenes = [
        {
            "id": str(i),
            "title": "",
            "setting": "s" * 500,
            "character_ids": [],
            "beats": [{"id": str(j), "action": "a" * 1000, "change": "c" * 1000} for j in range(6)],
        }
        for i in range(2)
    ]
    with pytest.raises(ValidationError, match="12000"):
        SaveChapterPlan(**document(scenes=scenes))


def unit_service(plan=None):
    repository = Mock()
    repository.get.return_value = plan
    structure = Mock()
    structure.get_chapter.return_value = SimpleNamespace(project_id="project")
    characters = Mock()
    bibles = Mock()
    rules = Mock(return_value=())
    service = ChapterPlanningService(repository, structure, characters, bibles, Mock(), rules)
    return SimpleNamespace(
        service=service, repository=repository, characters=characters, bibles=bibles, rules=rules
    )


def test_context_absent_plan_and_rule_sources_and_changed_plan():
    s = unit_service()
    assert s.service.context_sources("chapter") == ()
    plan = saved_document(writing_rule_revision_ids=["rule-version"])
    s.repository.get.return_value = plan
    rule = ContextSource(
        "writing_rules", (("rule", "rule-version"),), "保持行动衔接", "作者选择", None, False
    )
    s.rules.return_value = (rule,)
    assert s.service.context_sources("chapter")[-1] == rule
    s.rules.assert_called_once_with("project", ("rule-version",))
    s.repository.get.side_effect = [plan, saved_document(revision_id="new-revision")]
    with pytest.raises(AIContextChanged):
        s.service.context_sources("chapter")
    s.repository.get.side_effect = [plan, None]
    with pytest.raises(AIContextChanged):
        s.service.context_sources("chapter")


def test_bounded_assets_explicitly_report_truncation_and_omission():
    scene = {**document()["scenes"][0], "character_ids": ["character"]}
    s = unit_service(saved_document(scenes=[scene], include_story_bible=True))
    s.characters.get_character.return_value = SimpleNamespace(
        character_id="character",
        project_id="project",
        current_revision_id="cr",
        name="船夫",
        role="",
        profile="人" * 13000,
    )
    s.bibles.get_story_bible_for_project.return_value = SimpleNamespace(
        story_bible_id="bible", current_revision_id="br", title="港口", content="设定"
    )
    sources = s.service.context_sources("chapter")
    assert len(sources[1].text) == 12000 and sources[1].truncated
    assert sources[2].text == "" and sources[2].truncated and sources[2].omitted_reason
    s.rules.side_effect = PlanningReferenceInvalid
    with pytest.raises(AIContextChanged):
        s.service.context_sources("chapter")


def test_planning_http_guards_and_unavailable_dependency(workflow):
    w = workflow
    url = w.base + "/planning"
    assert w.client.put(url, json=document()).status_code == 403
    bad_media = w.client.put(url, headers={**w.headers, "Content-Type": "text/plain"}, content="{}")
    assert bad_media.status_code == 415
    w.app.state.chapter_planning_service = None
    missing = w.client.get(url)
    assert missing.status_code == 503 and missing.json()["error"]["code"] == "PLANNING_UNAVAILABLE"
    w.app.state.ai_workflow_schema_required = True
    upgrade = w.client.get(url)
    assert (
        upgrade.status_code == 503
        and upgrade.json()["error"]["code"] == "AI_WORKFLOW_SCHEMA_REQUIRED"
    )
