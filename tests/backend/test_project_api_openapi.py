"""Project route inventory and development OpenAPI contract tests."""

from pathlib import Path

import pytest
from tests.backend.factories import create_test_app

pytestmark = pytest.mark.unit


def test_project_route_inventory_contains_only_four_business_routes(tmp_path: Path) -> None:
    app = create_test_app(
        data_root=(tmp_path / "routes").resolve(),
        expose_api_docs=True,
    )
    project_routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if "/projects" in path
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }

    assert project_routes == {
        ("GET", "/api/v1/projects"),
        ("POST", "/api/v1/projects"),
        ("GET", "/api/v1/projects/{project_id}"),
        ("PUT", "/api/v1/projects/{project_id}"),
    }


def test_openapi_has_strict_project_contract_without_internal_types(tmp_path: Path) -> None:
    app = create_test_app(
        data_root=(tmp_path / "openapi").resolve(),
        expose_api_docs=True,
    )
    schema = app.openapi()
    paths = schema["paths"]
    put = paths["/api/v1/projects/{project_id}"]["put"]

    assert paths["/api/v1/projects"]["post"]["responses"].get("201") is not None
    assert paths["/api/v1/projects/{project_id}"]["get"]["responses"].get("404") is not None
    assert set(put["responses"]) >= {"200", "400", "404", "412", "422", "428", "503"}
    if_match = next(item for item in put["parameters"] if item["name"] == "If-Match")
    assert if_match["required"] is True
    assert "complete" in put["description"].lower()
    project_schema = {path: operations for path, operations in paths.items() if "/projects" in path}
    serialized = str(
        {
            "paths": project_schema,
            "create": schema["components"]["schemas"]["CreateProjectRequest"],
            "revise": schema["components"]["schemas"]["ReviseProjectRequest"],
            "response": schema["components"]["schemas"]["ProjectResponse"],
        }
    ).lower()
    assert "sqlalchemy" not in serialized
    assert "projectrecord" not in serialized
    assert "csrf_token" not in serialized
    create_schema = schema["components"]["schemas"]["CreateProjectRequest"]["properties"]
    assert set(create_schema) == {"title", "description"}


def test_production_openapi_remains_disabled(tmp_path: Path) -> None:
    app = create_test_app(
        data_root=(tmp_path / "production").resolve(),
        environment="production",
        expose_api_docs=False,
    )
    assert app.openapi_url is None
