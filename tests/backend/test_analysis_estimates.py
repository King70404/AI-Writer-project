"""Analysis and review previews use frozen messages and never open a usage attempt."""

import pytest
from tests.backend.test_ai_workflow import workflow
from tests.backend.test_candidate_edits_budget import put_budget
from tests.backend.test_story_memory import prepare
from tests.backend.test_usage_ledger import rows, transport

__all__ = ["workflow"]


def task(w, kind):
    if kind == "reference":
        path = f"/api/v1/projects/{w.project}/writing/references"
        created = w.client.post(
            path,
            headers=w.headers,
            json={
                "title": "范文",
                "text": "旅人停住脚步。",
                "profile_id": "default-local",
                "granularity": "sentence",
            },
        )
        assert created.status_code == 201, created.text
        item = created.json()
        return path + f"/{item['id']}", "/analyze", item
    item = prepare(w)
    return w.base + f"/memory/reviews/{item['id']}", "/send", item


@pytest.mark.parametrize("kind", ["reference", "review"])
def test_preview_off_warn_strict_never_sends_or_opens_ledger(workflow, monkeypatch, kind):
    w = workflow
    path, action, item = task(w, kind)
    calls = transport(monkeypatch)
    initial = w.client.get(path + "/estimate")
    assert initial.status_code == 200, initial.text
    result = initial.json()
    assert result["decision"] == "allowed" and result["budget_mode"] == "off"
    assert result["price"] is None and result["estimated_cost_upper"] is None
    assert result["input_tokens_upper"] >= result["input_characters"] > 0
    assert (
        result["output_tokens_upper"]
        == w.app.state.model_gateway_service.get_profile("default-local").max_output_tokens
    )
    assert "content" not in result and "messages" not in result
    put_budget(w, mode="warn", task_limit="1")
    warning = w.client.get(path + "/estimate").json()
    assert warning["decision"] == "warning" and "PRICE_MISSING" in warning["reasons"]
    put_budget(w, version=1, mode="strict", task_limit="1")
    refused = w.client.get(path + "/estimate").json()
    assert refused["decision"] == "refused"
    response = w.client.post(
        path + action,
        headers=w.headers,
        json={"expected_version": item["version"], "cloud_consent": False},
    )
    assert response.status_code == 409, response.text
    assert calls == [] and rows(w) == []
