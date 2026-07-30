"""Character HTTP dependency parsing and safe composition boundaries."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from tests.backend.character_http_support import PROJECT_ID

from aiwebnovel.character.application.services import (
    CharacterCommandService,
    CharacterQueryService,
)
from aiwebnovel.character.web.dependencies import (
    get_character_command_service,
    get_character_id,
    get_character_list_query,
    get_character_project_id,
    get_character_query_service,
    get_required_character_version,
    require_character_json,
)
from aiwebnovel.core.errors import AppError


def _request(
    *,
    headers: tuple[tuple[bytes, bytes], ...] = (),
    query: bytes = b"",
    app: FastAPI | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": query,
            "headers": list(headers),
            "client": ("127.0.0.1", 1),
            "server": ("127.0.0.1", 80),
            "app": app or FastAPI(),
        }
    )


def test_path_identifier_dependencies_are_strict() -> None:
    assert get_character_project_id(PROJECT_ID) == PROJECT_ID
    with pytest.raises(AppError) as project_error:
        get_character_project_id("bad")
    with pytest.raises(AppError) as character_error:
        get_character_id("bad")
    assert project_error.value.code == "INVALID_PROJECT_ID"
    assert character_error.value.code == "INVALID_CHARACTER_ID"


@pytest.mark.parametrize(
    ("headers", "code"),
    [
        ((), "PRECONDITION_REQUIRED"),
        (
            ((b"if-match", b'"1"'), (b"if-match", b'"1"')),
            "INVALID_IF_MATCH",
        ),
        (((b"if-match", b'W/"1"'),), "INVALID_IF_MATCH"),
    ],
)
def test_if_match_dependency_rejects_missing_duplicate_and_weak(
    headers: tuple[tuple[bytes, bytes], ...],
    code: str,
) -> None:
    with pytest.raises(AppError) as error:
        get_required_character_version(_request(headers=headers))
    assert error.value.code == code
    assert int(get_required_character_version(_request(headers=((b"if-match", b'"2"'),)))) == 2


@pytest.mark.parametrize(
    "headers",
    [
        (),
        ((b"content-type", b"application/json"), (b"content-type", b"application/json")),
        ((b"content-type", "application/jsön".encode()),),
        ((b"content-type", b"text/plain"),),
        ((b"content-type", b"application/json; charset=latin-1"),),
    ],
)
def test_json_dependency_rejects_noncanonical_media_types(
    headers: tuple[tuple[bytes, bytes], ...],
) -> None:
    with pytest.raises(AppError) as error:
        require_character_json(_request(headers=headers))
    assert error.value.code == "UNSUPPORTED_MEDIA_TYPE"
    assert (
        require_character_json(
            _request(headers=((b"content-type", b"application/json; charset=utf-8"),))
        )
        is None
    )


@pytest.mark.parametrize(
    "query",
    [
        b"other=1",
        b"limit=1&limit=2",
        b"limit=",
        b"limit=%EF%BC%91",
        b"limit=101",
        b"cursor=x&cursor=y",
        b"cursor=invalid",
    ],
)
def test_list_query_dependency_rejects_ambiguous_inputs(query: bytes) -> None:
    with pytest.raises(AppError):
        get_character_list_query(_request(query=query), PROJECT_ID)
    default = get_character_list_query(_request(), PROJECT_ID)
    assert default.limit == 20
    assert default.after is None


def test_composed_service_dependencies_require_exact_service_instances(
    tmp_path: Path,
) -> None:
    app = FastAPI()
    request = _request(app=app)
    with pytest.raises(AppError):
        get_character_command_service(request)
    with pytest.raises(AppError):
        get_character_query_service(request)
    command = CharacterCommandService(object(), lambda: None, lambda: None, lambda: None)  # type: ignore[arg-type]
    query = CharacterQueryService(object(), object())  # type: ignore[arg-type]
    app.state.character_command_service = command
    app.state.character_query_service = query
    assert get_character_command_service(request) is command
    assert get_character_query_service(request) is query
