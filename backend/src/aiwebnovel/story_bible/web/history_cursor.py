"""Canonical Story Bible-bound cursors for immutable revision history."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Never

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.story_bible.application.history_models import (
    StoryBibleRevisionHistoryPosition,
)
from aiwebnovel.story_bible.identifiers import StoryBibleId

STORY_BIBLE_REVISION_CURSOR_VERSION = 1
MAX_STORY_BIBLE_REVISION_CURSOR_LENGTH = 256
_BASE64URL = re.compile(r"\A[A-Za-z0-9_-]+\Z")
_PAYLOAD_KEYS = frozenset({"v", "story_bible_id", "after_revision_number"})


class InvalidStoryBibleRevisionCursor(ValueError):
    """Raised without echoing an invalid Story Bible revision cursor."""

    def __init__(self) -> None:
        super().__init__("The Story Bible revision cursor is invalid.")


def _reject_json_constant(_value: str) -> Never:
    raise InvalidStoryBibleRevisionCursor


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidStoryBibleRevisionCursor
        result[key] = value
    return result


def encode_story_bible_revision_cursor(
    position: StoryBibleRevisionHistoryPosition,
) -> str:
    """Encode one position as canonical compact unpadded Base64url text."""
    if type(position) is not StoryBibleRevisionHistoryPosition:
        raise TypeError("position must be a StoryBibleRevisionHistoryPosition")
    payload = {
        "v": STORY_BIBLE_REVISION_CURSOR_VERSION,
        "story_bible_id": str(position.story_bible_id),
        "after_revision_number": int(position.revision_number),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_story_bible_revision_cursor(
    cursor: object,
    *,
    story_bible_id: str,
) -> StoryBibleRevisionHistoryPosition:
    """Decode one canonical cursor and bind it to the requested Story Bible."""
    try:
        StoryBibleId.parse(story_bible_id)
    except (DomainError, TypeError, ValueError):
        raise InvalidStoryBibleRevisionCursor from None
    if (
        type(cursor) is not str
        or not cursor
        or len(cursor) > MAX_STORY_BIBLE_REVISION_CURSOR_LENGTH
        or not cursor.isascii()
        or _BASE64URL.fullmatch(cursor) is None
    ):
        raise InvalidStoryBibleRevisionCursor
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        raise InvalidStoryBibleRevisionCursor from None
    try:
        payload = json.loads(
            decoded.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidStoryBibleRevisionCursor):
        raise InvalidStoryBibleRevisionCursor from None
    if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS:
        raise InvalidStoryBibleRevisionCursor
    version = payload.get("v")
    payload_story_bible_id = payload.get("story_bible_id")
    after_revision_number = payload.get("after_revision_number")
    if (
        type(version) is not int
        or version != STORY_BIBLE_REVISION_CURSOR_VERSION
        or type(payload_story_bible_id) is not str
        or payload_story_bible_id != story_bible_id
        or type(after_revision_number) is not int
    ):
        raise InvalidStoryBibleRevisionCursor
    try:
        position = StoryBibleRevisionHistoryPosition(
            story_bible_id=StoryBibleId.parse(payload_story_bible_id),
            revision_number=RevisionNumber(after_revision_number),
        )
    except (DomainError, TypeError, ValueError):
        raise InvalidStoryBibleRevisionCursor from None
    if encode_story_bible_revision_cursor(position) != cursor:
        raise InvalidStoryBibleRevisionCursor
    return position


__all__ = [
    "MAX_STORY_BIBLE_REVISION_CURSOR_LENGTH",
    "STORY_BIBLE_REVISION_CURSOR_VERSION",
    "InvalidStoryBibleRevisionCursor",
    "decode_story_bible_revision_cursor",
    "encode_story_bible_revision_cursor",
]
