"""Character production OpenAPI surface is exact and bounded."""

from pathlib import Path

from tests.backend.ai_workflow_contract_support import (
    AI_WORKFLOW_OPERATIONS,
    BACKUP_OPERATIONS,
    CANDIDATE_BUDGET_OPERATIONS,
    STORY_MEMORY_OPERATIONS,
    USAGE_OPERATIONS,
    WORKBENCH_OPERATIONS,
    WRITING_PREPARATION_OPERATIONS,
)
from tests.backend.character_http_support import isolated_app


def test_production_api_has_exactly_thirty_eight_operations_and_six_character_routes(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    operations = {
        (method.upper(), path)
        for path, path_operations in app.openapi()["paths"].items()
        for method in path_operations
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert len(operations) == 84
    assert len(AI_WORKFLOW_OPERATIONS) == 13
    assert len(WRITING_PREPARATION_OPERATIONS) == 9
    assert len(BACKUP_OPERATIONS) == 5
    assert len(WORKBENCH_OPERATIONS) == 5
    assert len(USAGE_OPERATIONS) == 1
    assert len(CANDIDATE_BUDGET_OPERATIONS) == 8
    assert operations >= AI_WORKFLOW_OPERATIONS | (
        WRITING_PREPARATION_OPERATIONS
        | STORY_MEMORY_OPERATIONS
        | BACKUP_OPERATIONS
        | WORKBENCH_OPERATIONS
        | USAGE_OPERATIONS
        | CANDIDATE_BUDGET_OPERATIONS
    )
    assert {
        ("GET", "/api/v1/projects/{project_id}/characters"),
        ("POST", "/api/v1/projects/{project_id}/characters"),
        ("GET", "/api/v1/characters/{character_id}"),
        ("PUT", "/api/v1/characters/{character_id}"),
        ("GET", "/api/v1/characters/{character_id}/revisions"),
        ("GET", "/api/v1/characters/{character_id}/revisions/{revision_number}"),
    }.issubset(operations)
    assert not any(
        method != "GET" and "/characters/" in path and "/revisions" in path
        for method, path in operations
    )
    schema = app.openapi()
    assert "/api/v1/characters/{character_id}" in schema["paths"]
    assert "patch" not in schema["paths"]["/api/v1/characters/{character_id}"]
    assert (
        "ETag"
        in schema["paths"]["/api/v1/characters/{character_id}"]["get"]["responses"]["200"][
            "headers"
        ]
    )
    assert "428" in schema["paths"]["/api/v1/characters/{character_id}"]["put"]["responses"]
    assert "If-Match" in {
        parameter["name"]
        for parameter in schema["paths"]["/api/v1/characters/{character_id}"]["put"]["parameters"]
    }
