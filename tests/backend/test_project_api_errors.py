"""Safe Project error mapping and request-validation privacy tests."""

import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.project_api_support import isolated_app, issue_write_headers

from aiwebnovel.core.errors import AppError
from aiwebnovel.domain.errors import ConcurrencyConflict, InvalidDomainIdentifier
from aiwebnovel.project.errors import (
    InvalidProjectDescription,
    InvalidProjectTitle,
    ProjectAlreadyExists,
    ProjectDataCorruption,
    ProjectNotFound,
    ProjectRepositoryError,
)
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.project.web.dependencies import get_project_command_service
from aiwebnovel.project.web.errors import raise_project_http_error

pytestmark = pytest.mark.integration


class _UnusedCommandService:
    def create_project(self, command: object) -> object:
        raise AssertionError("Pydantic failures must not call the service")


@pytest.mark.parametrize(
    ("failure", "status_code", "code"),
    [
        (InvalidDomainIdentifier(), 422, "INVALID_PROJECT_ID"),
        (InvalidProjectTitle(), 422, "INVALID_PROJECT_TITLE"),
        (InvalidProjectDescription(), 422, "INVALID_PROJECT_DESCRIPTION"),
        (
            ProjectNotFound(ProjectId.parse("prj_00000000000000000000000001")),
            404,
            "PROJECT_NOT_FOUND",
        ),
        (
            ProjectAlreadyExists(ProjectId.parse("prj_00000000000000000000000001")),
            409,
            "PROJECT_ALREADY_EXISTS",
        ),
        (
            ConcurrencyConflict(expected_version=1, actual_version=2),
            412,
            "PROJECT_VERSION_CONFLICT",
        ),
        (ProjectDataCorruption(), 500, "PROJECT_DATA_CORRUPTION"),
        (ProjectRepositoryError(), 503, "PROJECT_PERSISTENCE_UNAVAILABLE"),
    ],
)
def test_known_project_failures_map_to_fixed_app_errors(
    failure: Exception, status_code: int, code: str
) -> None:
    with pytest.raises(AppError) as raised:
        raise_project_http_error(failure)

    assert raised.value.status_code == status_code
    assert raised.value.code == code
    assert str(failure) not in raised.value.details


def test_unknown_project_failure_is_not_misclassified() -> None:
    failure = RuntimeError("unknown-canary")
    with pytest.raises(RuntimeError) as raised:
        raise_project_http_error(failure)
    assert raised.value is failure


def test_pydantic_422_never_echoes_input_or_context(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    app.dependency_overrides[get_project_command_service] = lambda: _UnusedCommandService()
    canary = f"BODY-{secrets.token_hex(16)}"

    with TestClient(app) as client:
        headers = issue_write_headers(client)
        response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": 7, "description": canary, "secret": canary},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert canary not in response.text
    errors = response.json()["error"]["details"]["errors"]
    assert errors
    assert all(set(error) == {"field", "type", "message"} for error in errors)


def test_unmigrated_project_api_is_safe_503_while_live_remains_available(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    canary = "NO-SUCH-TABLE-CANARY"

    with TestClient(app, raise_server_exceptions=False) as client:
        headers = issue_write_headers(client)
        live = client.get("/api/v1/health/live")
        response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"title": canary, "description": canary},
        )

    assert live.status_code == 200
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROJECT_PERSISTENCE_UNAVAILABLE"
    lowered = response.text.lower()
    assert canary.lower() not in lowered
    assert "no such table" not in lowered
    assert ".sqlite" not in lowered
