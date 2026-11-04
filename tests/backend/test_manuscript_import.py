"""Real database import workflow and transaction tests."""

from uuid import uuid4

from tests.backend.test_ai_workflow import workflow

__all__ = ["workflow"]


def test_import_preview_chunk_commit_and_recovery(workflow):
    w = workflow
    text = "序言\r\n第一章 雨夜\r\n你好😀\r\n第二章 渡口\r\n再见"
    begin = w.client.post("/api/v1/imports/uploads", headers=w.headers, json={"mode": "auto"})
    assert begin.status_code == 200, begin.text
    upload = begin.json()["upload_id"]
    endpoint = f"/api/v1/imports/uploads/{upload}/chunks"
    a = w.client.put(endpoint, headers=w.headers, json={"offset": 0, "text": text[:8]})
    assert a.status_code == 200, a.text
    assert (
        w.client.put(endpoint, headers=w.headers, json={"offset": 0, "text": text[:8]}).status_code
        == 200
    )
    assert (
        w.client.put(endpoint, headers=w.headers, json={"offset": 1, "text": "oops"}).status_code
        == 409
    )
    b = w.client.put(endpoint, headers=w.headers, json={"offset": 8, "text": text[8:]})
    assert b.status_code == 200, b.text
    preview = w.client.post(f"/api/v1/imports/uploads/{upload}/finish", headers=w.headers, json={})
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["source_text"] == text
    assert data["original_line_endings_normalized"] is True
    assert [x["title"] for x in data["chapters"]] == ["序言", "第一章 雨夜", "第二章 渡口"]
    payload = {
        "preview_version": data["version"],
        "source_sha256": data["source_sha256"],
        "idempotency_key": str(uuid4()),
        "title": "导入书",
    }
    result = w.client.post(f"/api/v1/imports/{upload}/commit", headers=w.headers, json=payload)
    assert result.status_code == 200, result.text
    assert (
        w.client.post(f"/api/v1/imports/{upload}/commit", headers=w.headers, json=payload).json()
        == result.json()
    )
    changed = dict(payload, title="不同")
    assert (
        w.client.post(
            f"/api/v1/imports/{upload}/commit", headers=w.headers, json=changed
        ).status_code
        == 409
    )
    assert w.client.get(f"/api/v1/imports/{upload}/receipt").json() == result.json()
    chapter = w.client.get(f"/api/v1/chapters/{result.json()['first_chapter_id']}/content")
    assert chapter.status_code == 200, chapter.text
    assert chapter.json()["content"] == "序言\n"


def test_preview_refuses_lost_source_and_stale_versions(workflow):
    w = workflow
    upload = w.client.post(
        "/api/v1/imports/uploads", headers=w.headers, json={"mode": "single"}
    ).json()["upload_id"]
    w.client.put(
        f"/api/v1/imports/uploads/{upload}/chunks",
        headers=w.headers,
        json={"offset": 0, "text": "原文不丢"},
    )
    data = w.client.post(
        f"/api/v1/imports/uploads/{upload}/finish", headers=w.headers, json={}
    ).json()
    endpoint = f"/api/v1/imports/{upload}/preview"
    bad = {
        "expected_version": 1,
        "chapters": [{"title": "正文", "start": 0, "body_start": 1, "end": 4}],
    }
    assert w.client.put(endpoint, headers=w.headers, json=bad).status_code == 422
    good = {
        "expected_version": 1,
        "chapters": [
            {"title": "第一段", "start": 0, "body_start": 0, "end": 2},
            {"title": "第二段", "start": 2, "body_start": 2, "end": 4},
        ],
    }
    response = w.client.put(endpoint, headers=w.headers, json=good)
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert w.client.put(endpoint, headers=w.headers, json=good).status_code == 409
    assert (
        w.client.post(
            f"/api/v1/imports/{upload}/commit",
            headers=w.headers,
            json={
                "preview_version": 1,
                "source_sha256": data["source_sha256"],
                "idempotency_key": str(uuid4()),
                "title": "书",
            },
        ).status_code
        == 409
    )


def test_failed_import_rolls_back_all_records(workflow, monkeypatch):
    import pytest
    from sqlalchemy import func, select

    import aiwebnovel.imports.service as module
    from aiwebnovel.project.persistence.models import ProjectRecord

    w = workflow
    upload = w.client.post(
        "/api/v1/imports/uploads", headers=w.headers, json={"mode": "auto"}
    ).json()["upload_id"]
    w.client.put(
        f"/api/v1/imports/uploads/{upload}/chunks",
        headers=w.headers,
        json={"offset": 0, "text": "第一章 一\n甲\n第二章 二\n乙"},
    )
    data = w.client.post(
        f"/api/v1/imports/uploads/{upload}/finish", headers=w.headers, json={}
    ).json()
    factory = w.app.state.database_session_factory
    with factory() as session:
        before = session.scalar(select(func.count()).select_from(ProjectRecord))
    actual = module.chapter_aggregate_to_records
    count = 0

    def broken(chapter):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("injected failure")
        return actual(chapter)

    monkeypatch.setattr(module, "chapter_aggregate_to_records", broken)
    with pytest.raises(RuntimeError):
        w.client.post(
            f"/api/v1/imports/{upload}/commit",
            headers=w.headers,
            json={
                "preview_version": 1,
                "source_sha256": data["source_sha256"],
                "idempotency_key": str(uuid4()),
                "title": "回滚测试",
            },
        )
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ProjectRecord)) == before
    assert w.client.get(f"/api/v1/imports/{upload}/receipt").status_code == 404


def test_import_chunk_boundaries_and_explicit_limit(workflow, monkeypatch):
    import aiwebnovel.imports.service as module

    w = workflow
    upload = w.client.post(
        "/api/v1/imports/uploads", headers=w.headers, json={"mode": "single"}
    ).json()["upload_id"]
    endpoint = f"/api/v1/imports/uploads/{upload}/chunks"
    monkeypatch.setattr(module, "MAX_BYTES", 10)
    assert (
        w.client.put(endpoint, headers=w.headers, json={"offset": 0, "text": "汉字😀"}).status_code
        == 200
    )
    assert (
        w.client.put(endpoint, headers=w.headers, json={"offset": 3, "text": "x"}).status_code
        == 413
    )
    preview = w.client.post(f"/api/v1/imports/uploads/{upload}/finish", headers=w.headers, json={})
    assert preview.status_code == 200
    assert preview.json()["source_text"] == "汉字😀"


def test_expired_uncommitted_uploads_are_pruned_but_receipts_survive(workflow):
    from datetime import UTC, datetime, timedelta

    from aiwebnovel.imports.persistence import ImportPreviewRecord

    w = workflow
    url = "/api/v1/imports/uploads"
    stale = w.client.post(url, headers=w.headers, json={"mode": "single"}).json()["upload_id"]
    committed = w.client.post(url, headers=w.headers, json={"mode": "single"}).json()["upload_id"]
    w.client.put(f"{url}/{committed}/chunks", headers=w.headers, json={"offset": 0, "text": "原文"})
    data = w.client.post(f"{url}/{committed}/finish", headers=w.headers, json={}).json()
    response = w.client.post(
        f"/api/v1/imports/{committed}/commit",
        headers=w.headers,
        json={
            "preview_version": 1,
            "source_sha256": data["source_sha256"],
            "idempotency_key": str(uuid4()),
            "title": "保留回执",
        },
    )
    assert response.status_code == 200
    with w.app.state.database_session_factory() as session:
        for token in (stale, committed):
            session.get(ImportPreviewRecord, token).expires_at = datetime.now(UTC) - timedelta(
                days=1
            )
        session.commit()
    assert w.client.post(url, headers=w.headers, json={"mode": "single"}).status_code == 200
    with w.app.state.database_session_factory() as session:
        assert session.get(ImportPreviewRecord, stale) is None
        assert session.get(ImportPreviewRecord, committed) is not None
    assert w.client.get(f"/api/v1/imports/{committed}/receipt").json() == response.json()
