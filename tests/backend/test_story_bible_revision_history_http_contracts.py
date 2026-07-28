"""Strict Story Bible history DTO, dependency, mapper, and router tests."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from aiwebnovel.core.errors import AppError, register_error_handlers
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryItem,
    StoryBibleRevisionHistoryPage,
    StoryBibleRevisionHistoryPosition,
    StoryBibleRevisionSnapshot,
)
from aiwebnovel.story_bible.application.history_service import (
    StoryBibleRevisionHistoryQueryService,
)
from aiwebnovel.story_bible.errors import StoryBibleDataCorruption
from aiwebnovel.story_bible.identifiers import StoryBibleId
from aiwebnovel.story_bible.web.history_dependencies import (
    get_story_bible_revision_history_query,
    get_story_bible_revision_history_query_service,
    get_story_bible_revision_query,
)
from aiwebnovel.story_bible.web.history_dto import (
    StoryBibleRevisionHistoryItemResponse,
    StoryBibleRevisionHistoryPageResponse,
    StoryBibleRevisionResponse,
)
from aiwebnovel.story_bible.web.history_mappers import (
    story_bible_revision_history_response_from_page,
    story_bible_revision_response_from_snapshot,
)
from aiwebnovel.story_bible.web.history_router import (
    create_story_bible_history_router,
)

pytestmark = pytest.mark.unit

STORY_BIBLE_ID = "sbl_00000000000000000000000001"
PROJECT_ID = "prj_00000000000000000000000002"
REVISION_ID = "sbr_00000000000000000000000003"
OTHER_REVISION_ID = "sbr_00000000000000000000000004"
NOW = datetime(2026, 7, 28, tzinfo=UTC)


def response_item(
    number: int = 2,
    *,
    revision_id: str = REVISION_ID,
    current: bool = True,
) -> StoryBibleRevisionHistoryItemResponse:
    return StoryBibleRevisionHistoryItemResponse(
        revision_id=revision_id,
        revision_number=number,
        title=f"Revision {number}",
        created_at=NOW,
        is_current=current,
    )


def response_page(**overrides: object) -> StoryBibleRevisionHistoryPageResponse:
    values: dict[str, object] = {
        "story_bible_id": STORY_BIBLE_ID,
        "project_id": PROJECT_ID,
        "current_revision_number": 2,
        "items": (response_item(),),
        "next_cursor": None,
        "has_more": False,
    }
    values.update(overrides)
    return StoryBibleRevisionHistoryPageResponse(**values)  # type: ignore[arg-type]


def response_revision(**overrides: object) -> StoryBibleRevisionResponse:
    values: dict[str, object] = {
        "story_bible_id": STORY_BIBLE_ID,
        "project_id": PROJECT_ID,
        "revision_id": REVISION_ID,
        "revision_number": 1,
        "title": "Original",
        "content": "Body",
        "created_at": NOW,
        "is_current": False,
        "current_revision_number": 2,
    }
    values.update(overrides)
    return StoryBibleRevisionResponse(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: response_item(revision_id="bad"),
        lambda: StoryBibleRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=0,
            title="x",
            created_at=NOW,
            is_current=True,
        ),
        lambda: StoryBibleRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=1,
            title="\x01",
            created_at=NOW,
            is_current=True,
        ),
        lambda: StoryBibleRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=1,
            title=" x ",
            created_at=NOW,
            is_current=True,
        ),
        lambda: StoryBibleRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=1,
            title="x",
            created_at=NOW.replace(tzinfo=None),
            is_current=True,
        ),
        lambda: response_page(story_bible_id="bad"),
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
        lambda: response_revision(story_bible_id="bad"),
        lambda: response_revision(project_id="bad"),
        lambda: response_revision(revision_id="bad"),
        lambda: response_revision(revision_number=0),
        lambda: response_revision(title="\x01"),
        lambda: response_revision(title=" x "),
        lambda: response_revision(content="\x01"),
        lambda: response_revision(content="line\r\n"),
        lambda: response_revision(created_at=NOW.replace(tzinfo=None)),
        lambda: response_revision(revision_number=3),
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
    assert page.items[0].title == "Revision 2"
    assert revision.content == "Body"
    with pytest.raises(ValidationError):
        StoryBibleRevisionHistoryItemResponse(
            revision_id=REVISION_ID,
            revision_number=True,
            title="x",
            created_at=NOW,
            is_current=True,
        )
    with pytest.raises(ValidationError):
        StoryBibleRevisionResponse(
            **revision.model_dump(),
            unexpected="value",
        )
    with pytest.raises(ValidationError):
        revision.title = "changed"


def request(query: bytes = b"", *, service: object = None) -> Request:
    app = SimpleNamespace(state=SimpleNamespace(story_bible_revision_history_query_service=service))
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
        (b"cursor=x&cursor=y", 400, "INVALID_STORY_BIBLE_REVISION_CURSOR"),
        (b"extra=1", 422, "REQUEST_VALIDATION_ERROR"),
    ],
)
def test_history_dependencies_reject_malformed_query(
    query: bytes,
    status: int,
    code: str,
) -> None:
    with pytest.raises(AppError) as captured:
        get_story_bible_revision_history_query(
            request(query),
            STORY_BIBLE_ID,
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
        get_story_bible_revision_query(STORY_BIBLE_ID, number)
    assert captured.value.status_code == 422


def test_dependencies_accept_defaults_cursor_and_composed_service() -> None:
    first = get_story_bible_revision_history_query(
        request(),
        STORY_BIBLE_ID,
    )
    assert first.limit == 20 and first.after is None
    service = StoryBibleRevisionHistoryQueryService(FailingReader())
    assert get_story_bible_revision_history_query_service(request(service=service)) is service
    with pytest.raises(AppError) as captured:
        get_story_bible_revision_history_query_service(request())
    assert captured.value.code == "STORY_BIBLE_HISTORY_SERVICE_UNAVAILABLE"
    exact = get_story_bible_revision_query(STORY_BIBLE_ID, "1")
    assert exact.revision_number == 1


def test_explicit_mappers_copy_fields_cursor_and_reject_wrong_types() -> None:
    position = StoryBibleRevisionHistoryPosition(
        StoryBibleId.parse(STORY_BIBLE_ID),
        RevisionNumber(1),
    )
    application_page = StoryBibleRevisionHistoryPage(
        story_bible_id=STORY_BIBLE_ID,
        project_id=PROJECT_ID,
        current_revision_number=2,
        items=(
            StoryBibleRevisionHistoryItem(
                revision_id=REVISION_ID,
                revision_number=2,
                title="Current",
                created_at=NOW,
                is_current=True,
            ),
            StoryBibleRevisionHistoryItem(
                revision_id=OTHER_REVISION_ID,
                revision_number=1,
                title="Original",
                created_at=NOW,
                is_current=False,
            ),
        ),
        next_position=position,
        has_more=True,
    )
    mapped_page = story_bible_revision_history_response_from_page(application_page)
    assert mapped_page.next_cursor is not None
    assert mapped_page.items[1].title == "Original"
    application_revision = StoryBibleRevisionSnapshot(
        STORY_BIBLE_ID,
        PROJECT_ID,
        OTHER_REVISION_ID,
        1,
        "Original",
        "Body",
        NOW,
        False,
        2,
    )
    assert story_bible_revision_response_from_snapshot(application_revision).content == "Body"
    with pytest.raises(TypeError):
        story_bible_revision_history_response_from_page(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        story_bible_revision_response_from_snapshot(object())  # type: ignore[arg-type]


class FailingReader:
    def list_revisions(self, *_args: object, **_kwargs: object) -> object:
        raise StoryBibleDataCorruption

    def get_revision(self, *_args: object, **_kwargs: object) -> object:
        raise StoryBibleDataCorruption


def test_router_maps_service_domain_errors_without_leaking() -> None:
    app = FastAPI()
    app.state.story_bible_revision_history_query_service = (
        StoryBibleRevisionHistoryQueryService(FailingReader())  # type: ignore[arg-type]
    )
    register_error_handlers(app)
    app.include_router(create_story_bible_history_router(api_prefix="/api/v1"))
    with TestClient(app, raise_server_exceptions=False) as client:
        listing = client.get(f"/api/v1/story-bibles/{STORY_BIBLE_ID}/revisions")
        exact = client.get(f"/api/v1/story-bibles/{STORY_BIBLE_ID}/revisions/1")
    assert listing.status_code == exact.status_code == 500
    assert listing.json()["error"]["code"] == "STORY_BIBLE_DATA_CORRUPTION"
    assert STORY_BIBLE_ID not in listing.text + exact.text
