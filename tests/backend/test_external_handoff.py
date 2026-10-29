"""External handoff must not write until explicit adoption."""

from uuid import uuid4

from tests.backend.test_ai_workflow import workflow

__all__ = ["workflow"]


def test_handoff_roundtrip(workflow):
    w = workflow
    root = w.base + "/handoffs"
    request = {"instruction": "续写", "include_manuscript": True}
    preview = w.client.post(root + "/preview", headers=w.headers, json=request)
    assert preview.status_code == 200, preview.text
    task = w.client.post(
        root,
        headers=w.headers,
        json={**request, "context_sha256": preview.json()["context_sha256"]},
    )
    assert task.status_code == 200, task.text
    task = task.json()
    payload = {
        "format_version": 1,
        "handoff_id": task["handoff_id"],
        "context_sha256": task["context_sha256"],
        "text": "旅人走过古桥。" * 30,
    }
    path = root + "/" + task["handoff_id"] + "/candidates"
    result = w.client.post(path, headers=w.headers, json=payload)
    assert result.status_code == 200, result.text
    assert w.client.post(path, headers=w.headers, json=payload).json() == result.json()
    assert w.client.get(w.base + "/content").json()["content"] == "雨😀雨。"
    key = str(uuid4())
    response = w.client.post(
        path + "/" + result.json()["candidate_id"] + "/adopt",
        headers={**w.headers, "If-Match": '"2"'},
        json={"idempotency_key": key},
    )
    assert response.status_code == 200, response.text
    assert w.client.get(w.base + "/content").json()["content"].endswith(payload["text"])
    assert not w.calls
