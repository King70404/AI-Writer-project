"""Story Bible immutable revision-history application and cursor contracts."""

import base64
import json
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone

import pytest

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.project.identifiers import ProjectId
from aiwebnovel.story_bible.application.errors import StoryBibleRevisionNotFound
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryItem,
    StoryBibleRevisionHistoryPage,
    StoryBibleRevisionHistoryPosition,
    StoryBibleRevisionSnapshot,
)
from aiwebnovel.story_bible.application.history_queries import (
    GetStoryBibleRevisionQuery,
    ListStoryBibleRevisionsQuery,
)
from aiwebnovel.story_bible.application.history_service import (
    StoryBibleRevisionHistoryQueryService,
)
from aiwebnovel.story_bible.errors import StoryBibleDataCorruption
from aiwebnovel.story_bible.identifiers import StoryBibleId
from aiwebnovel.story_bible.web.history_cursor import (
    MAX_STORY_BIBLE_REVISION_CURSOR_LENGTH,
    InvalidStoryBibleRevisionCursor,
    decode_story_bible_revision_cursor,
    encode_story_bible_revision_cursor,
)

pytestmark = pytest.mark.unit

STORY_BIBLE_ID = "sbl_00000000000000000000000001"
OTHER_STORY_BIBLE_ID = "sbl_00000000000000000000000002"
PROJECT_ID = "prj_00000000000000000000000003"
REVISION_ID = "sbr_00000000000000000000000004"
OTHER_REVISION_ID = "sbr_00000000000000000000000005"
NOW = datetime(2026, 7, 28, tzinfo=UTC)


def item(
    number: int = 2,
    *,
    revision_id: str = REVISION_ID,
    current: bool = True,
) -> StoryBibleRevisionHistoryItem:
    return StoryBibleRevisionHistoryItem(
        revision_id=revision_id,
        revision_number=number,
        title=f"Revision {number}",
        created_at=NOW,
        is_current=current,
    )


def position(number: int = 2) -> StoryBibleRevisionHistoryPosition:
    return StoryBibleRevisionHistoryPosition(
        StoryBibleId.parse(STORY_BIBLE_ID),
        RevisionNumber(number),
    )


def page() -> StoryBibleRevisionHistoryPage:
    return StoryBibleRevisionHistoryPage(
        story_bible_id=STORY_BIBLE_ID,
        project_id=PROJECT_ID,
        current_revision_number=2,
        items=(item(),),
        next_position=None,
        has_more=False,
    )


def snapshot() -> StoryBibleRevisionSnapshot:
    return StoryBibleRevisionSnapshot(
        story_bible_id=STORY_BIBLE_ID,
        project_id=PROJECT_ID,
        revision_id=REVISION_ID,
        revision_number=1,
        title="Original",
        content="Line one\nLine two",
        created_at=NOW,
        is_current=False,
        current_revision_number=2,
    )


def test_models_are_exact_frozen_detached_and_validate_invariants() -> None:
    summary = item()
    history = page()
    revision = snapshot()

    assert {field.name for field in fields(summary)} == {
        "revision_id",
        "revision_number",
        "title",
        "created_at",
        "is_current",
    }
    assert {field.name for field in fields(history)} == {
        "story_bible_id",
        "project_id",
        "current_revision_number",
        "items",
        "next_position",
        "has_more",
    }
    assert {field.name for field in fields(revision)} == {
        "story_bible_id",
        "project_id",
        "revision_id",
        "revision_number",
        "title",
        "content",
        "created_at",
        "is_current",
        "current_revision_number",
    }
    assert not hasattr(summary, "content")
    with pytest.raises(FrozenInstanceError):
        summary.title = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: item(revision_id="bad"),
        lambda: StoryBibleRevisionHistoryItem(REVISION_ID, True, "x", NOW, True),
        lambda: StoryBibleRevisionHistoryItem(REVISION_ID, 1, "\x01", NOW, True),
        lambda: StoryBibleRevisionHistoryItem(REVISION_ID, 1, "x", NOW.replace(tzinfo=None), True),
        lambda: StoryBibleRevisionHistoryPage(STORY_BIBLE_ID, PROJECT_ID, 2, [], None, False),
        lambda: StoryBibleRevisionHistoryPage(
            STORY_BIBLE_ID,
            PROJECT_ID,
            2,
            (item(1, current=False), item(2)),
            None,
            False,
        ),
        lambda: StoryBibleRevisionHistoryPage(
            STORY_BIBLE_ID,
            PROJECT_ID,
            2,
            (item(),),
            position(),
            False,
        ),
        lambda: StoryBibleRevisionSnapshot(
            STORY_BIBLE_ID,
            PROJECT_ID,
            REVISION_ID,
            3,
            "x",
            "body",
            NOW,
            False,
            2,
        ),
        lambda: StoryBibleRevisionSnapshot(
            STORY_BIBLE_ID,
            PROJECT_ID,
            REVISION_ID,
            1,
            "x",
            "body",
            NOW,
            True,
            2,
        ),
    ],
)
def test_models_reject_malformed_order_current_and_text(factory: object) -> None:
    with pytest.raises((DomainError, TypeError, ValueError)):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: StoryBibleRevisionHistoryPosition(
            STORY_BIBLE_ID,
            RevisionNumber(1),  # type: ignore[arg-type]
        ),
        lambda: StoryBibleRevisionHistoryItem(
            1,
            1,
            "x",
            NOW,
            True,  # type: ignore[arg-type]
        ),
        lambda: StoryBibleRevisionHistoryItem(
            "sbr_01arz3ndektsv4rrffq69g5fav",
            1,
            "x",
            NOW,
            True,
        ),
        lambda: StoryBibleRevisionHistoryItem(REVISION_ID, 0, "x", NOW, True),
        lambda: StoryBibleRevisionHistoryItem(
            REVISION_ID,
            1,
            1,
            NOW,
            True,  # type: ignore[arg-type]
        ),
        lambda: StoryBibleRevisionHistoryItem(REVISION_ID, 1, " x ", NOW, True),
        lambda: StoryBibleRevisionHistoryItem(
            REVISION_ID,
            1,
            "x",
            "bad",
            True,  # type: ignore[arg-type]
        ),
        lambda: StoryBibleRevisionHistoryItem(
            REVISION_ID,
            1,
            "x",
            NOW.astimezone(timezone(timedelta(hours=8))),
            True,
        ),
        lambda: StoryBibleRevisionHistoryItem(
            REVISION_ID,
            1,
            "x",
            NOW,
            1,  # type: ignore[arg-type]
        ),
        lambda: StoryBibleRevisionHistoryPage(
            STORY_BIBLE_ID,
            PROJECT_ID,
            2,
            (),
            None,
            1,  # type: ignore[arg-type]
        ),
        lambda: StoryBibleRevisionHistoryPage(
            STORY_BIBLE_ID,
            PROJECT_ID,
            2,
            (),
            object(),
            False,  # type: ignore[arg-type]
        ),
        lambda: StoryBibleRevisionHistoryPage(
            STORY_BIBLE_ID,
            PROJECT_ID,
            2,
            (
                item(2),
                item(2, revision_id=OTHER_REVISION_ID, current=True),
            ),
            None,
            False,
        ),
        lambda: StoryBibleRevisionHistoryPage(
            STORY_BIBLE_ID,
            PROJECT_ID,
            2,
            (
                item(2),
                item(1, revision_id=REVISION_ID, current=False),
            ),
            None,
            False,
        ),
        lambda: StoryBibleRevisionHistoryPage(
            STORY_BIBLE_ID,
            PROJECT_ID,
            2,
            (item(2, current=False),),
            None,
            False,
        ),
        lambda: StoryBibleRevisionHistoryPage(STORY_BIBLE_ID, PROJECT_ID, 2, (), position(), True),
        lambda: StoryBibleRevisionSnapshot(
            STORY_BIBLE_ID,
            PROJECT_ID,
            REVISION_ID,
            1,
            "x",
            "body",
            NOW,
            1,  # type: ignore[arg-type]
            2,
        ),
        lambda: StoryBibleRevisionSnapshot(
            STORY_BIBLE_ID,
            PROJECT_ID,
            REVISION_ID,
            1,
            1,  # type: ignore[arg-type]
            "body",
            NOW,
            False,
            2,
        ),
        lambda: StoryBibleRevisionSnapshot(
            STORY_BIBLE_ID,
            PROJECT_ID,
            REVISION_ID,
            1,
            " x ",
            "body",
            NOW,
            False,
            2,
        ),
        lambda: StoryBibleRevisionSnapshot(
            STORY_BIBLE_ID,
            PROJECT_ID,
            REVISION_ID,
            1,
            "x",
            1,  # type: ignore[arg-type]
            NOW,
            False,
            2,
        ),
        lambda: StoryBibleRevisionSnapshot(
            STORY_BIBLE_ID,
            PROJECT_ID,
            REVISION_ID,
            1,
            "x",
            "line\r\n",
            NOW,
            False,
            2,
        ),
    ],
)
def test_models_cover_every_strict_boundary(factory: object) -> None:
    with pytest.raises((DomainError, TypeError, ValueError)):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize("limit", [0, 101, True, 1.0, "1", None])
def test_queries_reject_invalid_limit(limit: object) -> None:
    with pytest.raises(ValueError):
        ListStoryBibleRevisionsQuery(
            STORY_BIBLE_ID,
            limit=limit,  # type: ignore[arg-type]
        )


def test_queries_reject_wrong_boundary_shapes() -> None:
    with pytest.raises(TypeError):
        ListStoryBibleRevisionsQuery(1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ListStoryBibleRevisionsQuery(
            STORY_BIBLE_ID,
            after=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError):
        GetStoryBibleRevisionQuery(1, 1)  # type: ignore[arg-type]
    for invalid in (0, True, 1.0, "1", 2**63):
        with pytest.raises(ValueError):
            GetStoryBibleRevisionQuery(
                STORY_BIBLE_ID,
                invalid,  # type: ignore[arg-type]
            )


class RecordingReader:
    def __init__(self, result: object) -> None:
        self.result = result
        self.list_calls: list[tuple[StoryBibleId, int, object]] = []
        self.get_calls: list[tuple[StoryBibleId, RevisionNumber]] = []

    def list_revisions(
        self,
        story_bible_id: StoryBibleId,
        *,
        limit: int,
        after: StoryBibleRevisionHistoryPosition | None,
    ) -> StoryBibleRevisionHistoryPage:
        self.list_calls.append((story_bible_id, limit, after))
        if isinstance(self.result, Exception):
            raise self.result
        assert isinstance(self.result, StoryBibleRevisionHistoryPage)
        return self.result

    def get_revision(
        self,
        story_bible_id: StoryBibleId,
        revision_number: RevisionNumber,
    ) -> StoryBibleRevisionSnapshot | None:
        self.get_calls.append((story_bible_id, revision_number))
        if isinstance(self.result, Exception):
            raise self.result
        assert self.result is None or isinstance(self.result, StoryBibleRevisionSnapshot)
        return self.result


def test_service_calls_each_reader_operation_once_and_preserves_errors() -> None:
    list_reader = RecordingReader(page())
    list_service = StoryBibleRevisionHistoryQueryService(list_reader)
    query = ListStoryBibleRevisionsQuery(STORY_BIBLE_ID, 7, position())
    assert list_service.list_revisions(query) == page()
    assert len(list_reader.list_calls) == 1
    assert list_reader.get_calls == []

    get_reader = RecordingReader(snapshot())
    get_service = StoryBibleRevisionHistoryQueryService(get_reader)
    assert get_service.get_revision(GetStoryBibleRevisionQuery(STORY_BIBLE_ID, 1)) == snapshot()
    assert len(get_reader.get_calls) == 1
    assert get_reader.list_calls == []

    failure = StoryBibleDataCorruption()
    failing_reader = RecordingReader(failure)
    with pytest.raises(StoryBibleDataCorruption) as captured:
        StoryBibleRevisionHistoryQueryService(failing_reader).list_revisions(
            ListStoryBibleRevisionsQuery(STORY_BIBLE_ID)
        )
    assert captured.value is failure


def test_service_rejects_invalid_inputs_without_reader_calls_and_maps_none() -> None:
    reader = RecordingReader(page())
    service = StoryBibleRevisionHistoryQueryService(reader)
    with pytest.raises(TypeError):
        service.list_revisions(object())  # type: ignore[arg-type]
    with pytest.raises(DomainError):
        service.list_revisions(ListStoryBibleRevisionsQuery("bad"))
    with pytest.raises(ValueError):
        service.list_revisions(
            ListStoryBibleRevisionsQuery(
                STORY_BIBLE_ID,
                after=StoryBibleRevisionHistoryPosition(
                    StoryBibleId.parse(OTHER_STORY_BIBLE_ID),
                    RevisionNumber(1),
                ),
            )
        )
    assert reader.list_calls == []

    absent = RecordingReader(None)
    with pytest.raises(StoryBibleRevisionNotFound):
        StoryBibleRevisionHistoryQueryService(absent).get_revision(
            GetStoryBibleRevisionQuery(STORY_BIBLE_ID, 9)
        )
    assert len(absent.get_calls) == 1
    with pytest.raises(TypeError):
        StoryBibleRevisionHistoryQueryService(absent).get_revision(
            object()  # type: ignore[arg-type]
        )


def encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def cursor_payload(**overrides: object) -> str:
    value: dict[str, object] = {
        "v": 1,
        "story_bible_id": STORY_BIBLE_ID,
        "after_revision_number": 20,
    }
    value.update(overrides)
    return encoded(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def test_cursor_round_trip_is_canonical_unpadded_and_bound() -> None:
    cursor = encode_story_bible_revision_cursor(position(20))
    assert decode_story_bible_revision_cursor(
        cursor,
        story_bible_id=STORY_BIBLE_ID,
    ) == position(20)
    assert all(character not in cursor for character in "=+/")
    with pytest.raises(InvalidStoryBibleRevisionCursor):
        decode_story_bible_revision_cursor(
            cursor,
            story_bible_id=OTHER_STORY_BIBLE_ID,
        )


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "a" * (MAX_STORY_BIBLE_REVISION_CURSOR_LENGTH + 1),
        "非",
        "abc=",
        "a",
        encoded(b"\xff"),
        encoded(b"not-json"),
        encoded(
            b'{"after_revision_number":NaN,"story_bible_id":"sbl_00000000000000000000000001","v":1}'
        ),
        encoded(b"x" * 193),
        encoded(b"[]"),
        encoded(b'{"after_revision_number":1,"story_bible_id":"x","v":1,"v":1}'),
        cursor_payload(extra=True),
        cursor_payload(v=2),
        cursor_payload(v=True),
        cursor_payload(story_bible_id="bad"),
        cursor_payload(after_revision_number=True),
        cursor_payload(after_revision_number=0),
        cursor_payload(after_revision_number=2**63),
        encoded(
            b'{ "after_revision_number":20,"story_bible_id":"sbl_00000000000000000000000001","v":1}'
        ),
    ],
)
def test_cursor_rejects_malformed_noncanonical_values(cursor: object) -> None:
    with pytest.raises(InvalidStoryBibleRevisionCursor) as captured:
        decode_story_bible_revision_cursor(
            cursor,
            story_bible_id=STORY_BIBLE_ID,
        )
    assert STORY_BIBLE_ID not in str(captured.value)


def test_cursor_rejects_wrong_encoder_type_and_requested_identity() -> None:
    with pytest.raises(TypeError):
        encode_story_bible_revision_cursor(object())  # type: ignore[arg-type]
    for candidate in ("bad", 1, None):
        with pytest.raises(InvalidStoryBibleRevisionCursor):
            decode_story_bible_revision_cursor(
                cursor_payload(),
                story_bible_id=candidate,  # type: ignore[arg-type]
            )


def test_identifiers_used_by_models_are_real_domain_values() -> None:
    assert type(position().story_bible_id) is StoryBibleId
    assert type(position().revision_number) is RevisionNumber
    assert type(ProjectId.parse(PROJECT_ID)) is ProjectId
