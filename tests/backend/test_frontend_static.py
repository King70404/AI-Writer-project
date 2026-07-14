"""Production frontend delivery, isolation, and path-safety tests."""

from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from aiwebnovel.core.config import Settings
from aiwebnovel.main import create_app


INDEX_MARKER = "AIWEBNOVEL_TEST_INDEX"


def _settings(
    tmp_path: Path,
    *,
    serve_frontend: bool,
    frontend_dist_path: Path,
    database_name: str = "frontend-static.sqlite3",
) -> Settings:
    return Settings(
        environment="test",
        serve_frontend=serve_frontend,
        frontend_dist_path=frontend_dist_path,
        database_url=str(
            URL.create(
                "sqlite+pysqlite", database=(tmp_path / database_name).as_posix()
            )
        ),
    )


def _create_build(path: Path) -> None:
    assets = path / "assets"
    assets.mkdir(parents=True)
    (path / "index.html").write_text(
        f"<!doctype html><title>{INDEX_MARKER}</title>", encoding="utf-8"
    )
    (assets / "test.js").write_text("console.log('asset-ok')\n", encoding="utf-8")
    (assets / "test.css").write_text("body { color: black; }\n", encoding="utf-8")


def test_static_service_is_disabled_by_default(tmp_path: Path) -> None:
    build = tmp_path / "unused-build"
    _create_build(build)
    app = create_app(
        _settings(
            tmp_path,
            serve_frontend=False,
            frontend_dist_path=build,
        )
    )

    with TestClient(app) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get("/api/v1/health/ready")
        root = client.get("/", headers={"Accept": "text/html"})

    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json()["checks"]["frontend"] == "not_required"
    assert root.status_code == 404
    assert root.json()["error"]["code"] == "NOT_FOUND"
    assert INDEX_MARKER not in root.text


def test_valid_build_serves_assets_and_constrained_spa_fallback(
    tmp_path: Path,
) -> None:
    build = tmp_path / "dist"
    _create_build(build)
    app = create_app(
        _settings(tmp_path, serve_frontend=True, frontend_dist_path=build)
    )

    with TestClient(app) as client:
        root = client.get("/", headers={"Accept": "text/html"})
        asset = client.get("/assets/test.js")
        stylesheet = client.get("/assets/test.css")
        future_route = client.get(
            "/future-client-route", headers={"Accept": "text/html"}
        )
        non_html_route = client.get(
            "/future-client-route", headers={"Accept": "application/json"}
        )
        live = client.get("/api/v1/health/live", headers={"Accept": "text/html"})
        ready = client.get("/api/v1/health/ready")
        missing_api = client.get(
            "/api/v1/missing", headers={"Accept": "text/html"}
        )
        reserved_api_paths = [
            client.get(path, headers={"Accept": "text/html"})
            for path in ("/api", "/api/", "/api/v1")
        ]
        missing_asset = client.get(
            "/assets/missing.js", headers={"Accept": "text/html"}
        )
        posted_route = client.post(
            "/future-client-route", headers={"Accept": "text/html"}
        )

    assert root.status_code == 200
    assert root.headers["content-type"].startswith("text/html")
    assert INDEX_MARKER in root.text
    assert asset.status_code == 200
    assert asset.text.strip() == "console.log('asset-ok')"
    assert "javascript" in asset.headers["content-type"]
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert future_route.status_code == 200
    assert INDEX_MARKER in future_route.text
    assert non_html_route.status_code == 404

    assert live.status_code == 200
    assert live.headers["content-type"].startswith("application/json")
    assert ready.status_code == 200
    assert ready.json()["checks"]["frontend"] == "ok"
    assert missing_api.status_code == 404
    assert missing_api.json()["error"]["code"] == "NOT_FOUND"
    assert all(response.status_code == 404 for response in reserved_api_paths)
    assert all(
        response.headers["content-type"].startswith("application/json")
        for response in reserved_api_paths
    )
    assert all(INDEX_MARKER not in response.text for response in reserved_api_paths)
    assert missing_asset.status_code == 404
    assert INDEX_MARKER not in missing_asset.text
    assert posted_route.status_code in {404, 405}
    assert INDEX_MARKER not in posted_route.text


def test_missing_or_invalid_build_keeps_api_live_but_fails_readiness(
    tmp_path: Path,
) -> None:
    missing_build = tmp_path / "private-missing-build"
    app = create_app(
        _settings(
            tmp_path,
            serve_frontend=True,
            frontend_dist_path=missing_build,
        )
    )

    with TestClient(app) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get("/api/v1/health/ready")
        root = client.get("/", headers={"Accept": "text/html"})

    assert live.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert ready.json()["checks"]["frontend"] == "failed"
    assert root.status_code == 503
    assert root.json()["error"]["code"] == "FRONTEND_BUILD_UNAVAILABLE"
    assert str(missing_build) not in root.text
    assert missing_build.name not in root.text
    assert "FileNotFoundError" not in root.text
    assert "Traceback" not in root.text


def test_build_without_assets_directory_is_not_ready(tmp_path: Path) -> None:
    invalid_build = tmp_path / "invalid-dist"
    invalid_build.mkdir()
    (invalid_build / "index.html").write_text(INDEX_MARKER, encoding="utf-8")
    app = create_app(
        _settings(
            tmp_path,
            serve_frontend=True,
            frontend_dist_path=invalid_build,
        )
    )

    with TestClient(app) as client:
        ready = client.get("/api/v1/health/ready")

    assert ready.status_code == 503
    assert ready.json()["checks"]["frontend"] == "failed"


def test_static_paths_cannot_escape_or_list_build_directories(tmp_path: Path) -> None:
    build = tmp_path / "dist"
    _create_build(build)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("DO_NOT_EXPOSE", encoding="utf-8")
    hidden = build / ".hidden"
    hidden.write_text("HIDDEN_VALUE", encoding="utf-8")
    app = create_app(
        _settings(tmp_path, serve_frontend=True, frontend_dist_path=build)
    )

    unsafe_paths = (
        "/../outside-secret.txt",
        "/%2e%2e/outside-secret.txt",
        "/%252e%252e/outside-secret.txt",
        "/assets/%2e%2e/%2e%2e/outside-secret.txt",
        "/assets/%255c..%255coutside-secret.txt",
        "/.hidden",
        "/assets/",
    )
    with TestClient(app) as client:
        responses = [
            client.get(path, headers={"Accept": "text/html"})
            for path in unsafe_paths
        ]

    assert all(response.status_code == 404 for response in responses)
    assert all("DO_NOT_EXPOSE" not in response.text for response in responses)
    assert all("HIDDEN_VALUE" not in response.text for response in responses)
    assert all(INDEX_MARKER not in response.text for response in responses)


def test_application_factories_keep_frontend_routes_and_status_isolated(
    tmp_path: Path,
) -> None:
    build = tmp_path / "isolated-dist"
    _create_build(build)
    disabled = create_app(
        _settings(
            tmp_path,
            serve_frontend=False,
            frontend_dist_path=build,
            database_name="disabled.sqlite3",
        )
    )
    enabled = create_app(
        _settings(
            tmp_path,
            serve_frontend=True,
            frontend_dist_path=build,
            database_name="enabled.sqlite3",
        )
    )

    disabled_paths = [route.path for route in disabled.routes]
    enabled_paths = [route.path for route in enabled.routes]
    assert Counter(disabled_paths)["/{frontend_path:path}"] == 0
    assert Counter(enabled_paths)["/{frontend_path:path}"] == 1

    with TestClient(disabled) as disabled_client:
        with TestClient(enabled) as enabled_client:
            disabled_ready = disabled_client.get("/api/v1/health/ready")
            enabled_ready = enabled_client.get("/api/v1/health/ready")
            disabled_root = disabled_client.get(
                "/", headers={"Accept": "text/html"}
            )
            enabled_root = enabled_client.get(
                "/", headers={"Accept": "text/html"}
            )

    assert disabled_ready.json()["checks"]["frontend"] == "not_required"
    assert enabled_ready.json()["checks"]["frontend"] == "ok"
    assert disabled_root.status_code == 404
    assert enabled_root.status_code == 200
    assert INDEX_MARKER in enabled_root.text
