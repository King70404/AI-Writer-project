"""Strict Character history DTO, dependency, mapper, and router tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from aiwebnovel.character.application.history_models import (
    CharacterRevisionHistoryItem,
    CharacterRevisionHistoryPage,
    CharacterRevisionHistoryPosition,
    CharacterRevisionSnapshot,
)
from aiwebnovel.character.application.history_service import (
    CharacterRevisionHistoryQueryService,
)
from aiwebnovel.character.errors import CharacterDataCorruption
from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.character.web.history_dependencies import (
    get_character_revision_history_query,
    get_character_revision_history_query_service,
    get_character_revision_query,
)
from aiwebnovel.character.web.history_dto import (
    CharacterRevisionHistoryItemResponse,
    CharacterRevisionHistoryPageResponse,
    CharacterRevisionResponse,
)
from aiwebnovel.character.web.history_mappers import (
    character_revision_history_response_from_page,
    character_revision_response_from_snapshot,
)
from aiwebnovel.character.web.history_router import (
    create_character_history_router,
)
from aiwebnovel.core.errors import AppError, register_error_handlers
from aiwebnovel.domain.revisions import RevisionNumber

pytestmark = pytest.mark.unit

CHARACTER_ID = "chr_00000000000000000000000001"
PROJECT_ID = "prj_00000000000000000000000002"
REVISION_ID = "crv_00000000000000000000000003"
OTHER_REVISION_ID = "crv_00000000000000000000000004"
NOW = datetime(2026, 7, 28, tzinfo=UTC)


def response_item(
    number: int = 2,
    *,
    revision_id: str = REVISION_ID,
    current: bool = True,
) -> CharacterRevisionHistoryItemResponse:
    return CharacterRevisionHistoryItemResponse(
        revision_id=revision_id,
        revision_number=number,
        name=f"Revision {number}",
        role="Lead",
        created_at=NOW,
        is_current=current,
    )


def response_page(**overrides: object) -> CharacterRevisionHistoryPageResponse:
    values: dict[str, object] = {
        "character_id": CHARACTER_ID,
        "project_id": PROJECT_ID,
        "current_revision_number": 2,
        "items": (response_item(),),
        "next_cursor": None,
        "has_more": False,
    }
    values.update(overrides)
    return CharacterRevisionHistoryPageResponse(**values)  # type: ignore[arg-type]


def response_revision(**overrides: object) -> CharacterRevisionResponse:
    values: dict[str, object] = {
        "character_id": CHARACTER_ID,
        "project_id": PROJECT_ID,
        "revision_id": REVISION_ID,
        "revision_number": 1,
        "name": "Original",
        "role": "Lead",
        "profile": "Body",
        "created_at": NOW,
        "is_current": False,
        "current_revision_number": 2,
    }
    values.update(overrides)
    return CharacterRevisionResponse(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: response_item(revision_id="bad"),
        lambda: CharacterRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=0,
            name="x",
            created_at=NOW,
            is_current=True,
        ),
        lambda: CharacterRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=1,
            name="\x01",
            created_at=NOW,
            is_current=True,
        ),
        lambda: CharacterRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=1,
            name=" x ",
            created_at=NOW,
            is_current=True,
        ),
        lambda: CharacterRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=1,
            name="x",
            created_at=NOW.replace(tzinfo=None),
            is_current=True,
        ),
        lambda: response_page(character_id="bad"),
        lambda: response_page(project_id="bad"),
        lambda: response_page(current_revision_number=0),
        lambda: response_page(next_cursor=""),
        lambda: response_page(next_cursor="x" * 257),
        lambda: response_page(next_cursor="非"),
        lambda: response_page(
            items=(
                response_item(1, current=False),
                response_item(2, current=True),
            )
        ),
        lambda: response_page(
            items=(
                response_item(),
                response_item(
                    1,
                    revision_id=REVISION_ID,
                    current=False,
                ),
            )
        ),
        lambda: response_page(items=(response_item(2, current=False),)),
        lambda: response_page(next_cursor="next", has_more=False),
        lambda: response_page(items=(), next_cursor="next", has_more=True),
        lambda: response_revision(character_id="bad"),
        lambda: response_revision(project_id="bad"),
        lambda: response_revision(revision_id="bad"),
        lambda: response_revision(revision_number=0),
        lambda: response_revision(name="\x01"),
        lambda: response_revision(name=" x "),
        lambda: response_revision(profile="\x01"),
        lambda: response_revision(profile="line\r\n"),
        lambda: response_revision(created_at=NOW.replace(tzinfo=None)),
        lambda: response_revision(is_current=True),
    ],
)
def test_dtos_reject_invalid_identifiers_text_time_page_and_current(
    factory: object,
) -> None:
    with pytest.raises(ValidationError):
        factory()  # type: ignore[operator]


def test_dtos_are_frozen_strict_and_forbid_extra() -> None:
    page = response_page()
    revision = response_revision()
    assert page.items[0].name == "Revision 2"
    assert revision.profile == "Body"
    with pytest.raises(ValidationError):
        CharacterRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=True,
            name="x",
            created_at=NOW,
            is_current=True,
        )
    with pytest.raises(ValidationError):
        CharacterRevisionResponse(
            **revision.model_dump(),
            unexpected="value",
        )
    with pytest.raises(ValidationError):
        revision.name = "changed"


def request(query: bytes = b"", *, service: object = None) -> Request:
    app = SimpleNamespace(state=SimpleNamespace(character_revision_history_query_service=service))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": query,
            "headers": [],
            "app": app,
        }
    )


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        (b"limit=1&limit=2", 422, "REQUEST_VALIDATION_ERROR"),
        (b"limit=999", 422, "REQUEST_VALIDATION_ERROR"),
        (b"cursor=x&cursor=y", 400, "INVALID_CHARACTER_REVISION_CURSOR"),
        (b"extra=1", 422, "REQUEST_VALIDATION_ERROR"),
    ],
)
def test_history_dependencies_reject_malformed_query(
    query: bytes,
    status: int,
    code: str,
) -> None:
    with pytest.raises(AppError) as captured:
        get_character_revision_history_query(
            request(query),
            CHARACTER_ID,
        )
    assert captured.value.status_code == status
    assert captured.value.code == code


@pytest.mark.parametrize(
    "number",
    ["", "0", "01", "-1", "1.0", "1e1", "非", str(2**63)],
)
def test_exact_revision_dependency_rejects_noncanonical_number(
    number: str,
) -> None:
    with pytest.raises(AppError) as captured:
        get_character_revision_query(CHARACTER_ID, number)
    assert captured.value.status_code == 422


def test_dependencies_accept_defaults_cursor_and_composed_service() -> None:
    first = get_character_revision_history_query(
        request(),
        CHARACTER_ID,
    )
    assert first.limit == 20 and first.after is None
    service = CharacterRevisionHistoryQueryService(FailingReader())
    assert get_character_revision_history_query_service(request(service=service)) is service
    with pytest.raises(AppError) as captured:
        get_character_revision_history_query_service(request())
    assert captured.value.code == "CHARACTER_HISTORY_SERVICE_UNAVAILABLE"
    exact = get_character_revision_query(CHARACTER_ID, "1")
    assert exact.revision_number == 1


def test_explicit_mappers_copy_fields_cursor_and_reject_wrong_types() -> None:
    position = CharacterRevisionHistoryPosition(
        CharacterId.parse(CHARACTER_ID),
        RevisionNumber(1),
    )
    application_page = CharacterRevisionHistoryPage(
        character_id=CHARACTER_ID,
        project_id=PROJECT_ID,
        current_revision_number=2,
        items=(
            CharacterRevisionHistoryItem(
                revision_id=REVISION_ID,
                revision_number=2,
                name="Current",
                role="Lead",
                created_at=NOW,
                is_current=True,
            ),
            CharacterRevisionHistoryItem(
                revision_id=OTHER_REVISION_ID,
                revision_number=1,
                name="Original",
                role="Lead",
                created_at=NOW,
                is_current=False,
            ),
        ),
        next_position=position,
        has_more=True,
    )
    mapped_page = character_revision_history_response_from_page(application_page)
    assert mapped_page.next_cursor is not None
    assert mapped_page.items[1].name == "Original"
    application_revision = CharacterRevisionSnapshot(
        CHARACTER_ID,
        PROJECT_ID,
        OTHER_REVISION_ID,
        1,
        "Original",
        "Lead",
        "Body",
        NOW,
        False,
        2,
    )
    assert character_revision_response_from_snapshot(application_revision).profile == "Body"
    with pytest.raises(TypeError):
        character_revision_history_response_from_page(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        character_revision_response_from_snapshot(object())  # type: ignore[arg-type]


class FailingReader:
    def list_revisions(self, *_args: object, **_kwargs: object) -> object:
        raise CharacterDataCorruption

    def get_revision(self, *_args: object, **_kwargs: object) -> object:
        raise CharacterDataCorruption


def test_router_maps_service_domain_errors_without_leaking() -> None:
    app = FastAPI()
    app.state.character_revision_history_query_service = (
        CharacterRevisionHistoryQueryService(FailingReader())  # type: ignore[arg-type]
    )
    register_error_handlers(app)
    app.include_router(create_character_history_router(api_prefix="/api/v1"))
    with TestClient(app, raise_server_exceptions=False) as client:
        listing = client.get(f"/api/v1/characters/{CHARACTER_ID}/revisions")
        exact = client.get(f"/api/v1/characters/{CHARACTER_ID}/revisions/1")
    assert listing.status_code == exact.status_code == 500
    assert listing.json()["error"]["code"] == "CHARACTER_DATA_CORRUPTION"
    assert CHARACTER_ID not in listing.text + exact.text


@pytest.mark.parametrize("role", ["\x01", " Role "])
def test_dtos_reject_invalid_or_noncanonical_character_role(role: str) -> None:
    with pytest.raises(ValidationError):
        CharacterRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=1,
            name="Name",
            role=role,
            created_at=NOW,
            is_current=True,
        )
