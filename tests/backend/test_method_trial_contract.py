"""F08 frozen comparisons and author-only assessment, without provider calls."""

from dataclasses import replace
from typing import Any, cast

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_candidate_edits_budget import put_budget
from tests.backend.test_chapter_planning import save
from tests.backend.test_usage_ledger import transport, usage
from tests.backend.test_writing_context_composition import rules
from tests.backend.test_writing_studio import studio

from aiwebnovel.ai_writing.application.models import GeneratedText
from aiwebnovel.ai_writing.application.workflow_models import ModelSnapshot
from aiwebnovel.novel_structure.application.queries import GetChapterContentQuery
from aiwebnovel.usage.attribution import current_usage_attribution
from aiwebnovel.usage.budget import BudgetRefused
from aiwebnovel.writing_studio.application.method_service import MethodService
from aiwebnovel.writing_studio.application.methods import (
    Baseline,
    MethodTemplate,
    Score,
    Trial,
    annotate,
    claim,
    display,
    finish,
    messages,
    score,
    template_rule,
)
from aiwebnovel.writing_studio.application.models import (
    WritingConflict,
    WritingInputInvalid,
    WritingRule,
)

__all__ = ["studio", "workflow"]


@pytest.fixture
def baseline():
    return Baseline(
        "p",
        "c",
        "revision",
        "plan",
        "rule-v1",
        "追逐场景",
        "作者的测试文字",
        "保存的规划",
        WritingRule("行动", "保持动作连续", "追逐", ("追逐",), "叙述总结", 4),
    )


def test_both_arms_freeze_the_same_source_and_only_rule_message_changes(baseline):
    without = messages(baseline, "without")
    with_rule = messages(baseline, "with")
    assert with_rule[:-1] == without
    assert with_rule[-1].content == "本次方法变量:保持动作连续"
    assert baseline.manuscript in without[1].content and baseline.plan in without[1].content


def test_annotation_is_bound_to_exact_rule_and_manuscript_revision(baseline):
    result = annotate(baseline, 0, 2, "embodied", "动作有延续")
    assert result.baseline.manuscript_revision_id == "revision"
    assert result.baseline.rule_version_id == "rule-v1"
    with pytest.raises(WritingInputInvalid):
        annotate(baseline, 0, len(baseline.manuscript) + 1, "embodied", "原因")
    with pytest.raises(WritingInputInvalid):
        annotate(baseline, 0, 2, "embodied", " ")
    long_baseline = replace(baseline, manuscript="文" * 50_001)
    assert annotate(long_baseline, 50_000, 50_001, "embodied", "末尾").end == 50_001
    with pytest.raises(WritingInputInvalid):
        messages(long_baseline, "without")


def test_template_copy_requires_author_confirmation_and_is_detached():
    template = MethodTemplate(
        "template", "source", "rule-v1", "节奏", "让动作产生后果", "追逐", "摘要", ("追逐",), 4
    )
    with pytest.raises(WritingInputInvalid):
        template_rule(template, confirmed=False)
    local = template_rule(template, confirmed=True)
    assert local.instruction == "让动作产生后果"
    del template
    assert local.name == "节奏" and local.scene_tags == ("追逐",)


def test_explicit_trial_sends_are_attributed_and_budget_refusal_stays_unsent(baseline):
    class Store:
        def __init__(self):
            self.trial = Trial(
                "trial",
                baseline,
                True,
                ModelSnapshot("p", "local", "local", "http://127.0.0.1:1", "fake", 100),
            )
            self.version = 1

        def get(self, project_id, trial_id):
            assert (project_id, trial_id) == ("p", "trial")
            return self.trial, self.version

        def mutate(self, project_id, trial_id, expected_version, transition):
            assert (project_id, trial_id, expected_version) == ("p", "trial", self.version)
            self.trial = transition(self.trial)
            self.version += 1
            return self.trial, self.version

    store = Store()
    calls = []

    def provider(profile, sent_messages, maximum, model):
        attribution = current_usage_attribution()
        calls.append((profile, sent_messages, attribution))
        if len(calls) == 1:
            raise BudgetRefused
        return GeneratedText("假候选", "fake")

    service = MethodService(
        cast(Any, store),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        provider,
        cast(Any, None),
        cast(Any, None),
    )
    with pytest.raises(BudgetRefused):
        service.send("p", "trial", slot="A", expected_version=1, cloud_consent=False)
    assert store.trial.with_rule.status == "ready"
    view = service.send("p", "trial", slot="A", expected_version=3, cloud_consent=False)
    assert view["a"] == {"status": "completed", "text": "假候选", "error": None}
    assert calls[-1][2].operation == "method_trial" and calls[-1][2].task_id == "trial"
    assert "a_uses_rule" not in view
    with pytest.raises(WritingConflict):
        service.send("p", "trial", slot="A", expected_version=5, cloud_consent=False)
    assert len(calls) == 2


def test_confirmed_rule_metadata_persists_versioned_without_model_calls(studio):
    payload = {
        "title": "动作",
        "reference_id": None,
        "confirmed": True,
        "rules": [
            {
                "name": "连续",
                "instruction": "让动作产生后果",
                "applies_to": "追逐",
                "scene_tags": ["追逐", "冲突"],
                "excludes": "静态回忆",
                "priority": 4,
            }
        ],
    }
    response = studio.client.post(studio.base + "/rules", headers=studio.headers, json=payload)
    assert response.status_code == 201, response.text
    original = response.json()
    assert original["rules"][0]["scene_tags"] == ["追逐", "冲突"]
    assert original["rules"][0]["excludes"] == "静态回忆"
    assert original["rules"][0]["priority"] == 4
    payload["expected_version"] = 1
    payload["rules"][0]["priority"] = 2
    revised = studio.client.post(
        studio.base + f"/rules/{original['rule_id']}/versions", headers=studio.headers, json=payload
    )
    assert revised.status_code == 201, revised.text
    versions = studio.client.get(studio.base + "/rules").json()
    assert [item["rules"][0]["priority"] for item in versions] == [4, 2]
    assert studio.calls == []


def test_real_http_trial_is_blind_metered_and_never_adopts(workflow, monkeypatch):
    w = workflow
    revision = rules(w)
    plan = save(w, writing_rule_revision_ids=[revision["id"]])
    content = w.app.state.novel_structure_query_service.get_chapter_content(
        GetChapterContentQuery(w.chapter)
    )
    url = f"/api/v1/projects/{w.project}/writing/method-trials"
    calls = transport(
        monkeypatch, GeneratedText("测试候选甲", "fake"), GeneratedText("测试候选乙", "fake")
    )
    prepared = w.client.post(
        url,
        headers=w.headers,
        json={
            "chapter_id": w.chapter,
            "manuscript_revision_id": content.current_revision_id,
            "plan_revision_id": plan["revision_id"],
            "rule_version_id": revision["id"],
            "rule_index": 0,
            "scene_id": "quay",
            "profile_id": "default-local",
        },
    )
    assert prepared.status_code == 201, prepared.text
    trial = prepared.json()
    assert "a_uses_rule" not in trial and calls == []
    assert w.client.get(url + f"/{trial['id']}/estimate/A").status_code == 200
    for slot in ("A", "B"):
        sent = w.client.post(
            url + f"/{trial['id']}/send",
            headers=w.headers,
            json={"slot": slot, "expected_version": trial["version"], "cloud_consent": False},
        )
        assert sent.status_code == 200, sent.text
        trial = sent.json()
        assert "a_uses_rule" not in trial
    assert len(calls) == 2
    assert {row["operation"] for row in usage(w)["items"]} == {"method_trial"}
    left, right = calls[0][1], calls[1][1]
    without, with_rule = sorted((left, right), key=len)
    assert with_rule[:-1] == without
    assert "本次方法变量" in with_rule[-1].content
    ratings = {
        "focus": 5,
        "continuity": 4,
        "subtext": 3,
        "persistence": 2,
        "originality": 1,
        "reason": "个人偏好",
    }
    rated = w.client.post(
        url + f"/{trial['id']}/rate",
        headers=w.headers,
        json={"expected_version": trial["version"], "a": ratings, "b": ratings},
    )
    assert rated.status_code == 200, rated.text
    assert isinstance(rated.json()["a_uses_rule"], bool)
    changed = w.client.post(
        f"/api/v1/projects/{w.project}/writing/rules/{revision['rule_id']}/versions",
        headers=w.headers,
        json={
            "title": "新版",
            "reference_id": None,
            "confirmed": True,
            "expected_version": 1,
            "rules": [{"name": "方法", "instruction": "修改后的方法", "applies_to": "场景"}],
        },
    )
    assert changed.status_code == 201, changed.text
    historical = w.client.get(url + f"/{trial['id']}").json()
    assert historical["rule_version_id"] == revision["id"]
    assert historical["a_score"] == ratings and historical["b_score"] == ratings
    assert w.client.get(w.base + "/content").json()["content"] == content.content
    assert len(calls) == 2


def test_trial_restart_marks_interrupted_without_transmitting(workflow):
    w = workflow
    revision = rules(w)
    plan = save(w)
    content = w.app.state.novel_structure_query_service.get_chapter_content(
        GetChapterContentQuery(w.chapter)
    )
    url = f"/api/v1/projects/{w.project}/writing/method-trials"
    prepared = w.client.post(
        url,
        headers=w.headers,
        json={
            "chapter_id": w.chapter,
            "manuscript_revision_id": content.current_revision_id,
            "plan_revision_id": plan["revision_id"],
            "rule_version_id": revision["id"],
            "rule_index": 0,
            "scene_id": "quay",
            "profile_id": "default-local",
        },
    )
    assert prepared.status_code == 201, prepared.text
    trial_id = prepared.json()["id"]
    store = w.app.state.writing_studio_service.method_service._store
    trial, _ = store.get(w.project, trial_id)
    slot_arm = "with" if trial.a_is_with else "without"
    store.mutate(w.project, trial_id, 1, lambda current: claim(current, slot_arm))
    store.recover_interrupted()
    recovered = w.client.get(url + f"/{trial_id}").json()
    assert recovered["a"]["status"] == "failed" and recovered["complete"] is False
    assert recovered["a"]["error"] == "AIProviderInterrupted"
    assert usage(w)["items"] == [] and w.calls == []


def test_strict_budget_refuses_trial_without_network_or_ledger(workflow, monkeypatch):
    w = workflow
    revision = rules(w)
    plan = save(w)
    content = w.app.state.novel_structure_query_service.get_chapter_content(
        GetChapterContentQuery(w.chapter)
    )
    put_budget(w, task_limit="1")
    calls = transport(monkeypatch)
    url = f"/api/v1/projects/{w.project}/writing/method-trials"
    prepared = w.client.post(
        url,
        headers=w.headers,
        json={
            "chapter_id": w.chapter,
            "manuscript_revision_id": content.current_revision_id,
            "plan_revision_id": plan["revision_id"],
            "rule_version_id": revision["id"],
            "rule_index": 0,
            "scene_id": "quay",
            "profile_id": "default-local",
        },
    )
    assert prepared.status_code == 201, prepared.text
    trial = prepared.json()
    estimate_a = w.client.get(url + f"/{trial['id']}/estimate/A").json()
    estimate_b = w.client.get(url + f"/{trial['id']}/estimate/B").json()
    assert estimate_a == estimate_b and estimate_a["decision"] == "refused"
    blocked = w.client.post(
        url + f"/{trial['id']}/send",
        headers=w.headers,
        json={"slot": "A", "expected_version": trial["version"], "cloud_consent": False},
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "AI_BUDGET_REFUSED"
    reloaded = w.client.get(url + f"/{trial['id']}").json()
    assert reloaded["a"]["status"] == "ready" and reloaded["version"] == 3
    assert calls == [] and usage(w)["items"] == []


def test_manual_annotation_and_cross_book_template_use_author_confirmation(workflow):
    w = workflow
    source = rules(w, instruction="来源书专属人物与情节不应自动复制")
    content = w.app.state.novel_structure_query_service.get_chapter_content(
        GetChapterContentQuery(w.chapter)
    )
    root = f"/api/v1/projects/{w.project}/writing"
    response = w.client.post(
        root + "/method-annotations",
        headers=w.headers,
        json={
            "chapter_id": w.chapter,
            "manuscript_revision_id": content.current_revision_id,
            "rule_version_id": source["id"],
            "rule_index": 0,
            "start": 0,
            "end": 2,
            "judgment": "embodied",
            "reason": "动作延续",
        },
    )
    assert response.status_code == 201, response.text
    entries = w.client.get(root + f"/method-annotations/{w.chapter}").json()
    assert len(entries) == 1 and entries[0]["manuscript_revision_id"] == content.current_revision_id
    assert "manuscript" not in entries[0] and entries[0]["rule_index"] == 0
    template = {
        "source_rule_version_id": source["id"],
        "source_rule_index": 0,
        "name": "动作",
        "instruction": "让动作产生后果",
        "applies_to": "冲突",
        "excludes": "摘要",
        "scene_tags": ["对话"],
        "priority": 4,
        "confirmed": True,
    }
    created = w.client.post(root + "/method-templates", headers=w.headers, json=template)
    assert created.status_code == 201, created.text
    assert "来源书专属人物与情节" not in created.text
    other = w.client.post(
        "/api/v1/projects", headers=w.headers, json={"title": "第二本合成书"}
    ).json()["project_id"]
    target = f"/api/v1/projects/{other}/writing"
    copy_url = target + f"/method-templates/{created.json()['id']}/copy"
    assert w.client.post(copy_url, headers=w.headers, json={"confirmed": False}).status_code == 422
    copied = w.client.post(copy_url, headers=w.headers, json={"confirmed": True})
    assert copied.status_code == 201, copied.text
    assert copied.json()["template_source_rule_version_id"] == source["id"]
    assert copied.json()["template_source_rule_index"] == 0
    assert "来源书专属人物与情节" not in copied.text
    deleted = w.client.request(
        "DELETE",
        target + f"/method-templates/{created.json()['id']}",
        headers={**w.headers, "Content-Type": "application/json"},
        content="{}",
    )
    assert deleted.status_code == 204, deleted.text
    assert w.client.get(target + "/rules").json()[0]["id"] == copied.json()["id"]
    assert w.calls == []


@pytest.mark.parametrize("a_is_with", [True, False])
def test_blind_display_reveals_assignment_only_after_author_scores(baseline, a_is_with):
    trial = Trial("id", baseline, a_is_with)
    trial = finish(claim(trial, "without"), "without", text="候选一", error=None)
    trial = finish(claim(trial, "with"), "with", text="候选二", error=None)
    assert "a_uses_rule" not in display(trial)
    rating = Score(5, 4, 3, 2, 1, "作者偏好")
    rated = score(trial, rating, rating)
    assert display(rated)["a_uses_rule"] is a_is_with
    assert rated.baseline.rule_version_id == "rule-v1"
    with pytest.raises(WritingConflict):
        score(rated, rating, rating)


def test_failed_arm_cannot_retry_or_be_scored(baseline):
    trial = Trial("id", baseline, False)
    trial = finish(claim(trial, "with"), "with", text=None, error="AIProviderUnavailable")
    assert display(trial)["complete"] is False
    with pytest.raises(WritingConflict):
        claim(trial, "with")
    with pytest.raises(WritingConflict):
        score(trial, Score(1, 1, 1, 1, 1, ""), Score(1, 1, 1, 1, 1, ""))
    assert (
        replace(trial.baseline.rule, instruction="新版本").instruction
        != trial.baseline.rule.instruction
    )
