"""HTTP validation, protected local requests, safe failures, and API inventory."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from tests.backend.ai_workflow_contract_support import (
    AI_WORKFLOW_OPERATIONS,
    BACKUP_OPERATIONS,
    STORY_MEMORY_OPERATIONS,
    USAGE_OPERATIONS,
    WORKBENCH_OPERATIONS,
    WRITING_PREPARATION_OPERATIONS,
)
from tests.backend.ai_writing_support import CHAPTER, FakeProvider, sources
from tests.backend.character_http_support import isolated_app, issue_write_headers

from aiwebnovel.ai_writing.application.services import AIWritingService
from aiwebnovel.ai_writing.errors import (
    AIContextChanged,
    AIProviderConfigurationInvalid,
    AIProviderInvalidResponse,
    AIProviderNotConfigured,
    AIProviderTimeout,
    AIProviderUnavailable,
    InvalidAIInput,
)
from aiwebnovel.ai_writing.web import get_ai_writing_service, require_json
from aiwebnovel.core.errors import AppError
from aiwebnovel.novel_structure.errors import ChapterNotFound, NovelStructureRepositoryError


@pytest.mark.parametrize(
    "operation,payload",
    [("continue", {}), ("rewrite", {"text": "多段\n正文", "instruction": "紧凑"})],
)
def test_http_candidate_shape_and_no_prompt_url_leak(
    tmp_path: Path, operation: str, payload: dict
) -> None:
    app = isolated_app(tmp_path)
    provider = FakeProvider()
    source = sources()
    service = AIWritingService(source.builder, provider)
    app.dependency_overrides[get_ai_writing_service] = lambda: service
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        response = client.post(
            f"/api/v1/chapters/{CHAPTER}/ai/{operation}", headers=headers, json=payload
        )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"operation", "text", "model", "context"}
    assert body["operation"] == operation and body["text"] == "候选正文\n第二段"
    assert set(body["context"]) == {
        "included_sources",
        "omitted_sources",
        "truncated",
        "character_count",
    }
    assert response.headers["cache-control"] == "no-store"
    assert "正文尾部" not in response.text and len(provider.calls) == 1


@pytest.mark.parametrize(
    "error,status",
    [
        (AIProviderNotConfigured, 503),
        (AIProviderConfigurationInvalid, 503),
        (AIProviderUnavailable, 502),
        (AIProviderInvalidResponse, 502),
        (AIProviderTimeout, 504),
        (AIContextChanged, 409),
        (InvalidAIInput, 422),
        (NovelStructureRepositoryError, 503),
        (ChapterNotFound, 404),
    ],
)
@pytest.mark.parametrize("operation", ["continue", "rewrite"])
def test_safe_error_mapping(
    tmp_path: Path, error: type[Exception], status: int, operation: str
) -> None:
    app = isolated_app(tmp_path)
    provider = FakeProvider(error())
    app.dependency_overrides[get_ai_writing_service] = lambda: AIWritingService(
        sources().builder, provider
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/chapters/{CHAPTER}/ai/{operation}",
            headers=issue_write_headers(client),
            json={"text": "text"} if operation == "rewrite" else {},
        )
    assert response.status_code == status
    assert not any(word in response.text for word in ("Traceback", "SQLAlchemy", "正文尾部"))


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("continue", {"instruction": None}),
        ("continue", {"instruction": True}),
        ("continue", {"instruction": "x" * 4001}),
        ("continue", {"instruction": "AI_WRITING_CANARY\x00"}),
        ("continue", {"extra": 1}),
        ("rewrite", {}),
        ("rewrite", {"text": ""}),
        ("rewrite", {"text": " "}),
        ("rewrite", {"text": False}),
        ("rewrite", {"text": "x" * 50001}),
    ],
)
def test_invalid_requests_do_not_invoke_provider(
    tmp_path: Path, operation: str, payload: dict
) -> None:
    app = isolated_app(tmp_path)
    p = FakeProvider()
    app.dependency_overrides[get_ai_writing_service] = lambda: AIWritingService(
        sources().builder, p
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/chapters/{CHAPTER}/ai/{operation}",
            headers=issue_write_headers(client),
            json=payload,
        )
    assert response.status_code == 422 and p.calls == []
    assert "AI_WRITING_CANARY" not in response.text


def test_not_found_invalid_id_security_media_type_and_unavailable(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    s = sources()
    p = FakeProvider()
    s.structure.get_chapter.side_effect = ChapterNotFound()
    app.dependency_overrides[get_ai_writing_service] = lambda: AIWritingService(s.builder, p)
    with TestClient(app) as client:
        url = f"/api/v1/chapters/{CHAPTER}/ai/continue"
        assert client.post(url, json={}).status_code == 403
        headers = issue_write_headers(client)
        assert client.post(url, headers=headers, json={}).status_code == 404
        assert (
            client.post("/api/v1/chapters/bad/ai/continue", headers=headers, json={}).status_code
            == 422
        )
        assert (
            client.post(
                url, headers={**headers, "Content-Type": "text/plain"}, content="{}"
            ).status_code
            == 415
        )
        app.dependency_overrides.clear()
        assert client.post(url, headers=headers, json={}).status_code == 503
    assert p.calls == []


def test_openapi_preserves_all_m5_operations_adds_exactly_two(tmp_path: Path) -> None:
    import json

    root = Path(__file__).resolve().parents[2]
    baseline = json.loads((root / "docs/M5_BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
    schema = isolated_app(tmp_path).openapi()
    operations = {
        (m.upper(), p)
        for p, item in schema["paths"].items()
        for m in item
        if m in {"get", "post", "put", "patch", "delete"}
    }
    old = {(i["method"], i["path"]) for i in baseline["production_api_operations"]}
    assert len(operations) == 76
    assert len(AI_WORKFLOW_OPERATIONS) == 13
    assert len(WRITING_PREPARATION_OPERATIONS) == 9
    assert len(BACKUP_OPERATIONS) == 5
    assert len(WORKBENCH_OPERATIONS) == 5
    assert len(USAGE_OPERATIONS) == 1
    assert operations >= AI_WORKFLOW_OPERATIONS
    assert operations >= (
        WRITING_PREPARATION_OPERATIONS
        | STORY_MEMORY_OPERATIONS
        | BACKUP_OPERATIONS
        | WORKBENCH_OPERATIONS
        | USAGE_OPERATIONS
    )
    assert operations - AI_WORKFLOW_OPERATIONS - (
        WRITING_PREPARATION_OPERATIONS
        | STORY_MEMORY_OPERATIONS
        | BACKUP_OPERATIONS
        | WORKBENCH_OPERATIONS
        | USAGE_OPERATIONS
    ) - old - {
        ("GET", "/api/v1/projects/{project_id}/export.txt"),
        ("POST", "/api/v1/projects/{project_id}/delete"),
    } == {
        ("POST", "/api/v1/chapters/{chapter_id}/ai/continue"),
        ("POST", "/api/v1/chapters/{chapter_id}/ai/rewrite"),
    }
    assert old <= operations
    assert schema["components"]["schemas"]["ContinueRequest"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"content-type", b"application/json"), (b"content-type", b"application/json")],
        [(b"content-type", b"\xff")],
        [(b"content-type", b"text/plain")],
        [(b"content-type", b"application/json;charset=ascii")],
    ],
)
def test_media_type_defensive_branches(headers: list) -> None:
    request = Request({"type": "http", "headers": headers})
    with pytest.raises(AppError) as caught:
        require_json(request)
    assert caught.value.status_code == 415


def test_uninitialized_service_is_safe_and_utf8_json_allowed() -> None:
    request = Request(
        {
            "type": "http",
            "headers": [(b"content-type", b"application/json; charset=UTF-8")],
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )
    assert require_json(request) is None
    with pytest.raises(AppError) as caught:
        get_ai_writing_service(request)
    assert caught.value.status_code == 503
