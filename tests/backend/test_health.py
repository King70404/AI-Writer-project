"""Health, request-ID, logging, and application-factory tests."""

from collections import Counter
from io import StringIO
import json
import logging

from fastapi.testclient import TestClient

from aiwebnovel.core.config import Settings
from aiwebnovel.core.logging import (
    JsonFormatter,
    bind_request_id,
    configure_logging,
    get_request_id,
    reset_request_id,
)
from aiwebnovel.core.middleware import is_valid_request_id
from aiwebnovel.main import create_app


def test_live_health_uses_configuration_and_returns_request_id() -> None:
    settings = Settings(
        app_name="HealthService",
        app_version="9.8.7",
        environment="test",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "HealthService",
        "version": "9.8.7",
    }
    assert is_valid_request_id(response.headers["X-Request-ID"])


def test_ready_health_reports_only_real_checks() -> None:
    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"configuration": "ok", "application": "ok"},
    }
    assert not ({"database", "codex", "model"} & response.json()["checks"].keys())


def test_request_ids_are_preserved_replaced_and_not_reused() -> None:
    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        preserved = client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "client.Safe-123:abc"}
        )
        invalid = client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "unsafe request id"}
        )
        too_long = client.get(
            "/api/v1/health/live", headers={"X-Request-ID": "a" * 129}
        )
        generated_one = client.get("/api/v1/health/live")
        generated_two = client.get("/api/v1/health/live")

    assert preserved.headers["X-Request-ID"] == "client.Safe-123:abc"
    assert invalid.headers["X-Request-ID"] != "unsafe request id"
    assert too_long.headers["X-Request-ID"] != "a" * 129
    assert is_valid_request_id(invalid.headers["X-Request-ID"])
    assert is_valid_request_id(too_long.headers["X-Request-ID"])
    assert generated_one.headers["X-Request-ID"] != generated_two.headers["X-Request-ID"]
    assert get_request_id() is None


def test_create_app_is_repeatable_without_duplicate_routes_or_handlers() -> None:
    first = create_app(Settings(environment="test"))
    second = create_app(Settings(environment="test"))

    first_paths = [route.path for route in first.routes]
    second_paths = [route.path for route in second.routes]
    assert first_paths == second_paths
    assert Counter(first_paths)["/api/v1/health/live"] == 1
    assert Counter(first_paths)["/api/v1/health/ready"] == 1

    logger = configure_logging("INFO")
    managed_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_aiwebnovel_json_handler", False)
    ]
    assert len(managed_handlers) == 1


def test_json_formatter_ignores_unserializable_extra_fields() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    record = logging.LogRecord(
        name="aiwebnovel.test",
        level=logging.INFO,
        pathname="test",
        lineno=1,
        msg="safe message",
        args=(),
        exc_info=None,
    )
    record.unserializable = object()

    token = bind_request_id("log-test-request")
    try:
        handler.handle(record)
    finally:
        reset_request_id(token)
    payload = json.loads(stream.getvalue())

    assert payload["message"] == "safe message"
    assert payload["logger"] == "aiwebnovel.test"
    assert payload["request_id"] == "log-test-request"
    assert get_request_id() is None
