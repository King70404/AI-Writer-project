"""Project list route inventory and OpenAPI contract."""

from pathlib import Path

import pytest
from tests.backend.ai_workflow_contract_support import (
    AI_WORKFLOW_OPERATIONS,
    BACKUP_OPERATIONS,
    CANDIDATE_BUDGET_OPERATIONS,
    HANDOFF_OPERATIONS,
    IMPORT_OPERATIONS,
    STORY_CONTROL_OPERATIONS,
    STORY_MEMORY_OPERATIONS,
    USAGE_OPERATIONS,
    WORKBENCH_OPERATIONS,
    WRITING_JOB_OPERATIONS,
    WRITING_PREPARATION_OPERATIONS,
)
from tests.backend.factories import create_test_app

pytestmark = pytest.mark.unit


def test_route_inventory_contains_all_declared_business_routes(tmp_path: Path) -> None:
    app = create_test_app(data_root=(tmp_path / "routes").resolve(), expose_api_docs=True)
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }
    expected_routes = {
        ("GET", "/api/v1/health/live"),
        ("GET", "/api/v1/health/ready"),
        ("GET", "/api/v1/security/session"),
        ("GET", "/api/v1/projects/{project_id}/export.txt"),
        ("GET", "/api/v1/projects"),
        ("POST", "/api/v1/projects"),
        ("GET", "/api/v1/projects/{project_id}"),
        ("PUT", "/api/v1/projects/{project_id}"),
        ("POST", "/api/v1/projects/{project_id}/delete"),
        ("GET", "/api/v1/projects/{project_id}/revisions"),
        ("GET", "/api/v1/projects/{project_id}/revisions/{revision_number}"),
        ("POST", "/api/v1/projects/{project_id}/story-bible"),
        ("GET", "/api/v1/projects/{project_id}/story-bible"),
        ("GET", "/api/v1/story-bibles/{story_bible_id}"),
        ("PUT", "/api/v1/story-bibles/{story_bible_id}"),
        ("GET", "/api/v1/story-bibles/{story_bible_id}/revisions"),
        (
            "GET",
            "/api/v1/story-bibles/{story_bible_id}/revisions/{revision_number}",
        ),
        ("GET", "/api/v1/projects/{project_id}/characters"),
        ("POST", "/api/v1/projects/{project_id}/characters"),
        ("GET", "/api/v1/characters/{character_id}"),
        ("PUT", "/api/v1/characters/{character_id}"),
        ("GET", "/api/v1/characters/{character_id}/revisions"),
        ("GET", "/api/v1/characters/{character_id}/revisions/{revision_number}"),
        ("POST", "/api/v1/projects/{project_id}/outline"),
        ("GET", "/api/v1/projects/{project_id}/outline"),
        ("PUT", "/api/v1/outlines/{outline_id}"),
        ("POST", "/api/v1/projects/{project_id}/volumes"),
        ("GET", "/api/v1/projects/{project_id}/volumes"),
        ("GET", "/api/v1/volumes/{volume_id}"),
        ("PUT", "/api/v1/volumes/{volume_id}"),
        ("POST", "/api/v1/projects/{project_id}/volumes/{volume_id}/chapters"),
        ("GET", "/api/v1/projects/{project_id}/volumes/{volume_id}/chapters"),
        ("GET", "/api/v1/chapters/{chapter_id}"),
        ("PUT", "/api/v1/chapters/{chapter_id}"),
        ("GET", "/api/v1/chapters/{chapter_id}/content"),
        ("PUT", "/api/v1/chapters/{chapter_id}/content"),
        ("POST", "/api/v1/chapters/{chapter_id}/ai/continue"),
        ("POST", "/api/v1/chapters/{chapter_id}/ai/rewrite"),
    }
    assert len(routes) == 157
    assert routes == expected_routes | AI_WORKFLOW_OPERATIONS | (
        WRITING_PREPARATION_OPERATIONS
        | STORY_MEMORY_OPERATIONS
        | BACKUP_OPERATIONS
        | WORKBENCH_OPERATIONS
        | USAGE_OPERATIONS
        | CANDIDATE_BUDGET_OPERATIONS
        | STORY_CONTROL_OPERATIONS
        | IMPORT_OPERATIONS
        | HANDOFF_OPERATIONS
        | WRITING_JOB_OPERATIONS
    )
    assert routes.isdisjoint(
        {
            ("POST", "/api/v1/characters/{character_id}/revisions"),
            ("PUT", "/api/v1/characters/{character_id}/revisions/{revision_number}"),
            ("PATCH", "/api/v1/characters/{character_id}/revisions/{revision_number}"),
            ("DELETE", "/api/v1/characters/{character_id}/revisions/{revision_number}"),
            ("POST", "/api/v1/characters/{character_id}/rollback"),
            ("POST", "/api/v1/characters/{character_id}/restore"),
        }
    )


def test_openapi_documents_fixed_keyset_contract_and_response(tmp_path: Path) -> None:
    app = create_test_app(data_root=(tmp_path / "openapi").resolve(), expose_api_docs=True)
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/projects"]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}

    assert operation["tags"] == ["Projects"]
    assert set(operation["responses"]) == {"200", "400", "422", "500", "503"}
    assert parameters["limit"]["schema"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 20,
    }
    assert parameters["cursor"]["required"] is False
    description = operation["description"].lower()
    for phrase in (
        "created_at desc",
        "project_id desc",
        "keyset",
        "not a security credential",
        "description",
        "total count",
        "search",
        "filtering",
        "custom sorting",
    ):
        assert phrase in description
    response_schema = schema["components"]["schemas"]["ProjectListResponse"]
    assert set(response_schema["properties"]) == {"items", "next_cursor", "has_more"}
    item_schema = schema["components"]["schemas"]["ProjectListItemResponse"]
    assert set(item_schema["properties"]) == {
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "created_at",
        "updated_at",
        "revision_created_at",
    }


def test_production_docs_remain_disabled_with_list_route_registered(tmp_path: Path) -> None:
    app = create_test_app(
        data_root=(tmp_path / "production").resolve(),
        environment="production",
        expose_api_docs=False,
    )
    assert app.openapi_url is None
    assert "get" in app.openapi()["paths"]["/api/v1/projects"]
