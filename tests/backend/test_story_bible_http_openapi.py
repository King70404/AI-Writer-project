"""Story Bible route inventory and OpenAPI contract tests."""

from pathlib import Path

import pytest
from tests.backend.ai_workflow_contract_support import (
    AI_WORKFLOW_OPERATIONS,
    WRITING_PREPARATION_OPERATIONS,
)
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


def test_production_api_inventory_has_exactly_fifty_routes(tmp_path: Path) -> None:
    app = create_test_app(data_root=(tmp_path / "routes").resolve(), expose_api_docs=True)
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert routes == EXPECTED_ROUTES | AI_WORKFLOW_OPERATIONS | WRITING_PREPARATION_OPERATIONS


def test_openapi_documents_six_story_bible_routes_and_exact_schemas(
    tmp_path: Path,
) -> None:
    app = create_test_app(data_root=(tmp_path / "schema").resolve(), expose_api_docs=True)
    schema = app.openapi()
    story_paths = {
        path: operations
        for path, operations in schema["paths"].items()
        if "story-bible" in path or "story-bibles" in path
    }
    assert set(story_paths) == {
        "/api/v1/projects/{project_id}/story-bible",
        "/api/v1/story-bibles/{story_bible_id}",
        "/api/v1/story-bibles/{story_bible_id}/revisions",
        "/api/v1/story-bibles/{story_bible_id}/revisions/{revision_number}",
    }
    assert set(story_paths["/api/v1/projects/{project_id}/story-bible"]) == {
        "get",
        "post",
    }
    assert set(story_paths["/api/v1/story-bibles/{story_bible_id}"]) == {
        "get",
        "put",
    }
    assert set(story_paths["/api/v1/story-bibles/{story_bible_id}/revisions"]) == {"get"}
    assert set(
        story_paths["/api/v1/story-bibles/{story_bible_id}/revisions/{revision_number}"]
    ) == {"get"}
    for operations in story_paths.values():
        assert all(operation["tags"] == ["Story Bible"] for operation in operations.values())

    components = schema["components"]["schemas"]
    assert set(components["CreateStoryBibleRequest"]["properties"]) == {"title", "content"}
    assert components["CreateStoryBibleRequest"]["required"] == ["title"]
    assert set(components["ReviseStoryBibleRequest"]["required"]) == {"title", "content"}
    assert set(components["StoryBibleResponse"]["properties"]) == {
        "story_bible_id",
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "content",
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    }
    assert "etag" not in components["StoryBibleResponse"]["properties"]
    put = story_paths["/api/v1/story-bibles/{story_bible_id}"]["put"]
    if_match = next(parameter for parameter in put["parameters"] if parameter["name"] == "If-Match")
    assert if_match["required"] is True
    assert {"400", "412", "428", "503"} <= set(put["responses"])
    descriptions = " ".join(
        operation["description"].lower()
        for operations in story_paths.values()
        for operation in operations.values()
    )
    for phrase in (
        "single allowed",
        "session",
        "csrf",
        "strong etag",
        "if-match",
        "patch",
        "revision history",
        "delete",
        "archive",
        "restore",
    ):
        assert phrase in descriptions


def test_production_docs_remain_disabled_with_story_bible_routes(
    tmp_path: Path,
) -> None:
    app = create_test_app(
        data_root=(tmp_path / "production").resolve(),
        environment="production",
        expose_api_docs=False,
    )
    assert app.openapi_url is None
    assert "put" in app.openapi()["paths"]["/api/v1/story-bibles/{story_bible_id}"]
