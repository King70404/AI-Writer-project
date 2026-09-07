"""Project revision-history route inventory and OpenAPI contract tests."""

from pathlib import Path

import pytest
from tests.backend.factories import create_test_app

pytestmark = pytest.mark.unit


EXPECTED_ROUTES = {
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
    ("GET", "/api/v1/story-bibles/{story_bible_id}/revisions/{revision_number}"),
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


def test_production_api_inventory_has_exactly_thirty_eight_routes(tmp_path: Path) -> None:
    app = create_test_app(data_root=(tmp_path / "routes").resolve(), expose_api_docs=True)
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert routes == EXPECTED_ROUTES


def test_openapi_documents_history_keyset_and_read_only_schemas(tmp_path: Path) -> None:
    app = create_test_app(data_root=(tmp_path / "schema").resolve(), expose_api_docs=True)
    schema = app.openapi()
    listing = schema["paths"]["/api/v1/projects/{project_id}/revisions"]["get"]
    exact = schema["paths"]["/api/v1/projects/{project_id}/revisions/{revision_number}"]["get"]
    parameters = {value["name"]: value for value in listing["parameters"]}

    assert listing["tags"] == exact["tags"] == ["Projects"]
    assert set(listing["responses"]) == {"200", "400", "404", "422", "500", "503"}
    assert set(exact["responses"]) == {"200", "404", "422", "500", "503"}
    assert parameters["limit"]["schema"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 20,
    }
    assert parameters["cursor"]["required"] is False
    description = listing["description"].lower()
    for phrase in (
        "revisionnumber desc",
        "keyset",
        "project-bound",
        "description",
        "total count",
        "not a security credential",
        "cannot be edited",
        "restored",
        "rolled back",
    ):
        assert phrase in description

    page_schema = schema["components"]["schemas"]["ProjectRevisionHistoryResponse"]
    assert set(page_schema["properties"]) == {
        "project_id",
        "current_revision_number",
        "items",
        "next_cursor",
        "has_more",
    }
    item_schema = schema["components"]["schemas"]["ProjectRevisionHistoryItemResponse"]
    assert set(item_schema["properties"]) == {
        "revision_id",
        "revision_number",
        "title",
        "created_at",
        "is_current",
    }
    revision_schema = schema["components"]["schemas"]["ProjectRevisionResponse"]
    assert "description" in revision_schema["properties"]
    assert "updated_at" not in revision_schema["properties"]
    assert "concurrency_version" not in revision_schema["properties"]


def test_production_docs_remain_disabled_with_history_routes_registered(
    tmp_path: Path,
) -> None:
    app = create_test_app(
        data_root=(tmp_path / "production").resolve(),
        environment="production",
        expose_api_docs=False,
    )
    assert app.openapi_url is None
    assert "get" in app.openapi()["paths"]["/api/v1/projects/{project_id}/revisions"]
