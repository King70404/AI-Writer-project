"""Tests for the frozen API error schema and safe failure handling."""

from collections.abc import Mapping
from typing import Any

from fastapi.testclient import TestClient

from aiwebnovel.core.config import Settings
from aiwebnovel.core.errors import AppError
from aiwebnovel.main import create_app


def assert_error_schema(payload: Mapping[str, Any]) -> None:
    assert set(payload) == {"error", "request_id"}
    assert set(payload["error"]) == {
        "code",
        "message",
        "details",
        "retryable",
        "suggested_action",
    }
    assert isinstance(payload["error"]["details"], dict)
    assert isinstance(payload["error"]["retryable"], bool)
    assert isinstance(payload["request_id"], str)


def test_unknown_path_uses_not_found_schema_and_matching_request_id() -> None:
    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        response = client.get("/api/v1/unknown", headers={"X-Request-ID": "client-404"})

    assert response.status_code == 404
    payload = response.json()
    assert_error_schema(payload)
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["request_id"] == "client-404"
    assert response.headers["X-Request-ID"] == payload["request_id"]


def test_validation_error_uses_controlled_details() -> None:
    app = create_app(Settings(environment="test"))

    @app.get("/_test/validation")
    async def validation_route(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/_test/validation", params={"value": "not-an-integer"})

    assert response.status_code == 422
    payload = response.json()
    assert_error_schema(payload)
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert set(payload["error"]["details"]) == {"errors"}
    assert response.headers["X-Request-ID"] == payload["request_id"]


def test_app_error_is_normalized() -> None:
    app = create_app(Settings(environment="test"))

    @app.get("/_test/app-error")
    async def app_error_route() -> None:
        raise AppError(
            code="TEST_CONFLICT",
            message="测试冲突。",
            status_code=409,
            details={"field": "revision"},
            suggested_action="刷新后重试。",
        )

    with TestClient(app) as client:
        response = client.get("/_test/app-error")

    assert response.status_code == 409
    payload = response.json()
    assert_error_schema(payload)
    assert payload["error"] == {
        "code": "TEST_CONFLICT",
        "message": "测试冲突。",
        "details": {"field": "revision"},
        "retryable": False,
        "suggested_action": "刷新后重试。",
    }
    assert response.headers["X-Request-ID"] == payload["request_id"]


def test_internal_error_is_generic_and_contains_no_diagnostics() -> None:
    app = create_app(Settings(environment="test"))

    @app.get("/_test/internal-error")
    async def internal_error_route() -> None:
        raise RuntimeError("sensitive diagnostic marker")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/_test/internal-error", headers={"X-Request-ID": "client-internal"}
        )

    assert response.status_code == 500
    payload = response.json()
    assert_error_schema(payload)
    assert payload["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "服务器内部错误。",
        "details": {},
        "retryable": False,
        "suggested_action": None,
    }
    assert payload["request_id"] == "client-internal"
    assert response.headers["X-Request-ID"] == payload["request_id"]
    assert "sensitive diagnostic marker" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
