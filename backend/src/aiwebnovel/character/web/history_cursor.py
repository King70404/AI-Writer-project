"""Canonical Character-bound cursors for immutable revision history."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Never

from aiwebnovel.character.application.history_models import CharacterRevisionHistoryPosition
from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.domain.revisions import RevisionNumber

CHARACTER_REVISION_CURSOR_VERSION = 1
MAX_CHARACTER_REVISION_CURSOR_LENGTH = 256
_BASE64URL = re.compile(r"\A[A-Za-z0-9_-]+\Z")
_PAYLOAD_KEYS = frozenset({"v", "character_id", "after_revision_number"})


class InvalidCharacterRevisionCursor(ValueError):
    def __init__(self) -> None:
        super().__init__("The Character revision cursor is invalid.")


def _reject_json_constant(_value: str) -> Never:
    raise InvalidCharacterRevisionCursor


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidCharacterRevisionCursor
        result[key] = value
    return result


def encode_character_revision_cursor(position: CharacterRevisionHistoryPosition) -> str:
    if type(position) is not CharacterRevisionHistoryPosition:
        raise TypeError("position must be a CharacterRevisionHistoryPosition")
    payload = {
        "v": CHARACTER_REVISION_CURSOR_VERSION,
        "character_id": str(position.character_id),
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


def decode_character_revision_cursor(
    cursor: object, *, character_id: str
) -> CharacterRevisionHistoryPosition:
    try:
        CharacterId.parse(character_id)
    except (DomainError, TypeError, ValueError):
        raise InvalidCharacterRevisionCursor from None
    if (
        type(cursor) is not str
        or not cursor
        or len(cursor) > MAX_CHARACTER_REVISION_CURSOR_LENGTH
        or not cursor.isascii()
        or _BASE64URL.fullmatch(cursor) is None
    ):
        raise InvalidCharacterRevisionCursor
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise InvalidCharacterRevisionCursor from None
    try:
        payload = json.loads(
            decoded.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidCharacterRevisionCursor):
        raise InvalidCharacterRevisionCursor from None
    if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS:
        raise InvalidCharacterRevisionCursor
    version = payload.get("v")
    payload_character_id = payload.get("character_id")
    after_revision_number = payload.get("after_revision_number")
    if (
        type(version) is not int
        or version != CHARACTER_REVISION_CURSOR_VERSION
        or type(payload_character_id) is not str
        or payload_character_id != character_id
        or type(after_revision_number) is not int
    ):
        raise InvalidCharacterRevisionCursor
    try:
        position = CharacterRevisionHistoryPosition(
            character_id=CharacterId.parse(payload_character_id),
            revision_number=RevisionNumber(after_revision_number),
        )
    except (DomainError, TypeError, ValueError):
        raise InvalidCharacterRevisionCursor from None
    if encode_character_revision_cursor(position) != cursor:
        raise InvalidCharacterRevisionCursor
    return position


__all__ = [
    "CHARACTER_REVISION_CURSOR_VERSION",
    "MAX_CHARACTER_REVISION_CURSOR_LENGTH",
    "InvalidCharacterRevisionCursor",
    "decode_character_revision_cursor",
    "encode_character_revision_cursor",
]
