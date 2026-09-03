"""Character production OpenAPI surface is exact and bounded."""

from pathlib import Path

from tests.backend.character_http_support import isolated_app


def test_production_api_has_exactly_thirty_four_operations_and_six_character_routes(
    tmp_path: Path,
) -> None:
    app = isolated_app(tmp_path)
    operations = {
        (method.upper(), path)
        for path, path_operations in app.openapi()["paths"].items()
        for method in path_operations
        if method in {"get", "post", "put", "patch", "delete"}
    }
    assert len(operations) == 34
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
