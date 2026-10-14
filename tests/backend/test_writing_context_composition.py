"""Selected immutable methods reach generation without sending reference prose."""

import pytest
from tests.backend.test_ai_workflow import create_run, generate, workflow
from tests.backend.test_chapter_planning import document

__all__ = ["workflow"]


def rules(w, instruction="先写迟疑的动作，再给出部分回答。", **changes):
    body = {
        "title": "本书的叙事方法",
        "reference_id": None,
        "rules": [{"name": "对话试探", "instruction": instruction, "applies_to": "盘问场景"}],
        "confirmed": True,
        **changes,
    }
    response = w.client.post(
        f"/api/v1/projects/{w.project}/writing/rules", headers=w.headers, json=body
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("operation", ["continue", "rewrite"])
def test_prepared_context_freezes_selected_rules_and_plan_after_later_changes(workflow, operation):
    w = workflow
    studio = f"/api/v1/projects/{w.project}/writing"
    reference = w.client.post(
        studio + "/references",
        headers=w.headers,
        json={
            "title": "仅用于学习的片段",
            "text": "范文独有的银色纸鹤停在钟摆上。",
            "granularity": "sentence",
            "profile_id": "default-local",
        },
    )
    assert reference.status_code == 201
    first = rules(w)
    plan = w.client.put(
        w.base + "/planning",
        headers=w.headers,
        json=document(writing_rule_revision_ids=[first["id"]]),
    )
    assert plan.status_code == 200
    arguments = {"operation": operation}
    if operation == "rewrite":
        arguments.update(selected_text="雨", selection_start=0, selection_end=1, max_steps=1)
    run = create_run(w, **arguments)
    assert "先写迟疑的动作" in run["context"]["text"]
    assert "银色纸鹤" not in run["context"]["text"]
    assert w.calls == []
    method = next(
        s for s in run["context"]["manifest"]["sources"] if s["source"] == "writing_rules"
    )
    assert method["references"] == [[first["rule_id"], first["id"]]]
    revised = w.client.post(
        studio + f"/rules/{first['rule_id']}/versions",
        headers=w.headers,
        json={
            "title": "新规则",
            "reference_id": None,
            "expected_version": 1,
            "rules": [{"name": "后果", "instruction": "留下物品损伤。", "applies_to": "冲突后"}],
            "confirmed": True,
        },
    )
    assert revised.status_code == 201
    new_plan = w.client.put(
        w.base + "/planning",
        headers=w.headers,
        json=document(expected_version=1, writing_rule_revision_ids=[revised.json()["id"]]),
    )
    assert new_plan.status_code == 200
    assert w.client.get(w.base + "/ai/runs/" + run["run_id"]).json()["context"] == run["context"]
    generated = generate(w, run)
    assert generated["candidates"][0]["status"] == "pending"
    system = w.calls[0][1][0].content
    assert "原创表达" in system and "目标字数指整章" in system
    assert ("下一小段" in system) == (operation == "continue")
    assert "银色纸鹤" not in "".join(m.content for m in w.calls[0][1])
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"
    next_run = create_run(w)
    assert "留下物品损伤" in next_run["context"]["text"]


def test_selected_rule_budget_exposes_truncation_and_omitted_versions(workflow):
    w = workflow
    long_rules = [
        {"name": str(i), "instruction": "方" * 1000, "applies_to": "适用"} for i in range(8)
    ]
    versions = [rules(w, rules=long_rules) for _ in range(3)]
    saved = w.client.put(
        w.base + "/planning",
        headers=w.headers,
        json=document(writing_rule_revision_ids=[v["id"] for v in versions]),
    )
    assert saved.status_code == 200
    run = create_run(w)
    selected = [s for s in run["context"]["manifest"]["sources"] if s["source"] == "writing_rules"]
    assert len(selected) == 3
    assert sum(len(s["text"]) for s in selected) == 8000
    assert selected[0]["truncated"]
    assert selected[1]["omitted_reason"] and selected[2]["omitted_reason"]
    assert run["context"]["manifest"]["truncated"]
