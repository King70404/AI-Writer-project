"""Security response-header and CSP tests for API, HTML, and static responses."""

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.testclient import TestClient

from aiwebnovel.security.headers import (
    BASE_SECURITY_HEADERS,
    CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)

pytestmark = pytest.mark.unit


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/test")
    async def api_response() -> JSONResponse:
        return JSONResponse({"status": "ok"}, headers={"Server": "secret/1.0"})

    @app.get("/")
    async def html_response() -> HTMLResponse:
        return HTMLResponse("<div id='root'></div>")

    @app.get("/assets/app.js")
    async def javascript_response() -> Response:
        return Response("console.log('ok')", media_type="text/javascript")

    @app.get("/assets/app.css")
    async def stylesheet_response() -> Response:
        return Response("body{}", media_type="text/css")

    app.add_middleware(SecurityHeadersMiddleware)
    return app


def _assert_base_headers(response: object) -> None:
    headers = response.headers  # type: ignore[attr-defined]
    for name, expected in BASE_SECURITY_HEADERS.items():
        assert headers[name] == expected


def test_api_response_has_no_store_and_no_server_header() -> None:
    with TestClient(_app()) as client:
        response = client.get("/api/test")
    assert response.status_code == 200
    _assert_base_headers(response)
    assert response.headers["Cache-Control"] == "no-store"
    assert "server" not in response.headers
    assert "content-security-policy" not in response.headers


def test_html_csp_is_complete_and_avoids_wildcards_or_unsafe_sources() -> None:
    with TestClient(_app()) as client:
        response = client.get("/")
    _assert_base_headers(response)
    assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert "unsafe-eval" not in CONTENT_SECURITY_POLICY
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
    assert "*" not in CONTENT_SECURITY_POLICY
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
    ):
        assert directive in CONTENT_SECURITY_POLICY


def test_javascript_css_and_static_404_retain_basic_headers() -> None:
    with TestClient(_app()) as client:
        javascript = client.get("/assets/app.js")
        stylesheet = client.get("/assets/app.css")
        missing = client.get("/assets/missing.png")
    assert javascript.status_code == 200
    assert stylesheet.status_code == 200
    assert missing.status_code == 404
    for response in (javascript, stylesheet, missing):
        _assert_base_headers(response)
    assert "content-security-policy" not in javascript.headers
    assert "content-security-policy" not in stylesheet.headers


def test_api_error_also_receives_security_headers() -> None:
    with TestClient(_app()) as client:
        response = client.get("/api/missing")
    assert response.status_code == 404
    _assert_base_headers(response)
    assert response.headers["Cache-Control"] == "no-store"
