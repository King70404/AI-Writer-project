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


def test_bound_run_charges_job_limit_and_rejects_direct_bypass(workflow):
    from tests.backend.test_ai_workflow import create_run, generate

    w = workflow
    response = w.client.post(
        f"/api/v1/projects/{w.project}/writing-jobs",
        headers=w.headers,
        json={
            "title": "限额任务",
            "chapter_ids": [w.chapter],
            "max_requests": 1,
            "max_output_characters": 600,
        },
    )
    assert response.status_code == 201, response.text
    job = response.json()
    run = create_run(w, max_steps=2, max_output_characters=600)
    job_path = f"/api/v1/writing-jobs/{job['job_id']}"
    bound = w.client.post(
        job_path + "/bind-run",
        headers=w.headers,
        json={"expected_version": 1, "run_id": run["run_id"]},
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["active_run_id"] == run["run_id"]
    assert not w.calls
    generated = generate(w, run)
    assert len(w.calls) == 1
    candidate = generated["candidates"][0]
    assert (
        w.client.post(
            w.base + f"/ai/candidates/{candidate['candidate_id']}/discard",
            headers=w.headers,
            json={},
        ).status_code
        == 200
    )
    second = w.client.post(
        w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
    )
    assert second.status_code == 409, second.text
    assert len(w.calls) == 1
    reread = w.client.get(job_path).json()
    assert reread["claimed_requests"] == 1
    assert reread["used_characters"] == candidate["character_count"]


def test_job_pause_cancel_and_pending_candidate(workflow):
    from tests.backend.test_ai_workflow import create_run, generate

    w = workflow
    job = w.client.post(
        f"/api/v1/projects/{w.project}/writing-jobs",
        headers=w.headers,
        json={"title": "交互", "chapter_ids": [w.chapter]},
    ).json()
    path = f"/api/v1/writing-jobs/{job['job_id']}"
    run = create_run(w, max_steps=2, max_output_characters=600)
    assert (
        w.client.post(
            path + "/bind-run",
            headers=w.headers,
            json={"expected_version": 1, "run_id": run["run_id"]},
        ).status_code
        == 200
    )
    assert (
        w.client.post(path + "/pause", headers=w.headers, json={"expected_version": 2}).status_code
        == 200
    )
    url = w.base + f"/ai/runs/{run['run_id']}/generate"
    assert w.client.post(url, headers=w.headers, json={}).status_code == 409
    assert not w.calls
    assert (
        w.client.post(path + "/resume", headers=w.headers, json={"expected_version": 3}).status_code
        == 200
    )
    output = generate(w, run)
    candidate = output["candidates"][0]
    assert (
        w.client.post(
            path + "/finish-step", headers=w.headers, json={"expected_version": 4}
        ).status_code
        == 409
    )
    w.service.adopt(w.chapter, candidate["candidate_id"], 2, "job-adopt-key")
    w.service.adopt(w.chapter, candidate["candidate_id"], 2, "job-adopt-key")
    after = w.client.get(path).json()
    assert after["generated_characters"] == candidate["character_count"]
    assert after["adopted_characters"] == candidate["character_count"]
    assert (
        w.client.post(path + "/cancel", headers=w.headers, json={"expected_version": 4}).status_code
        == 200
    )
    assert w.client.post(url, headers=w.headers, json={}).status_code == 409
    assert len(w.calls) == 1


def test_locally_refused_budget_returns_job_reservation(workflow):
    from tests.backend.test_ai_workflow import create_run

    from aiwebnovel.usage.budget import BudgetRefused

    w = workflow
    job = w.client.post(
        f"/api/v1/projects/{w.project}/writing-jobs",
        headers=w.headers,
        json={"title": "费用拒绝", "chapter_ids": [w.chapter], "max_requests": 1},
    ).json()
    path = f"/api/v1/writing-jobs/{job['job_id']}"
    run = create_run(w)
    assert (
        w.client.post(
            path + "/bind-run",
            headers=w.headers,
            json={"expected_version": 1, "run_id": run["run_id"]},
        ).status_code
        == 200
    )

    def refuse(*args):
        raise BudgetRefused

    w.service._provider = refuse
    result = w.client.post(
        w.base + f"/ai/runs/{run['run_id']}/generate", headers=w.headers, json={}
    )
    assert result.status_code == 409
    after = w.client.get(path).json()
    assert after["claimed_requests"] == 0 and after["used_characters"] == 0
