"""Author-driven multi-chapter plans never send model requests."""

from tests.backend.test_ai_workflow import workflow

__all__ = ["workflow"]


def test_manual_job_create_change_and_conflicts(workflow):
    w = workflow
    project, chapter = w.project, w.chapter
    url = f"/api/v1/projects/{project}/writing-jobs"
    created = w.client.post(
        url, headers=w.headers, json={"title": "第一轮", "chapter_ids": [chapter]}
    )
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] == "planned" and job["version"] == 1
    assert job["steps"] == [{"chapter_id": chapter, "status": "pending"}]
    assert len(w.client.get(url).json()) == 1
    path = f"/api/v1/writing-jobs/{job['job_id']}"
    assert w.client.get(path).json() == job
    assert (
        w.client.post(path + "/pause", headers=w.headers, json={"expected_version": 1}).json()[
            "status"
        ]
        == "paused"
    )
    assert (
        w.client.post(path + "/resume", headers=w.headers, json={"expected_version": 1}).status_code
        == 409
    )
    assert (
        w.client.post(path + "/resume", headers=w.headers, json={"expected_version": 2}).json()[
            "status"
        ]
        == "planned"
    )
    done = w.client.post(path + "/finish-step", headers=w.headers, json={"expected_version": 3})
    assert done.json()["status"] == "completed"
    assert done.json()["steps"][0]["status"] == "completed"
    assert (
        w.client.post(
            path + "/finish-step", headers=w.headers, json={"expected_version": 4}
        ).status_code
        == 409
    )
    assert (
        w.client.post(
            url, headers=w.headers, json={"title": "重复", "chapter_ids": [chapter, chapter]}
        ).status_code
        == 422
    )

