"""Canonical Project-bound HTTP cursors for Character list positions."""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import UTC, datetime
from typing import Never

from aiwebnovel.character.application.models import CharacterListPosition
from aiwebnovel.character.identifiers import CharacterId
from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.identifiers import ProjectId

CHARACTER_LIST_CURSOR_VERSION = 1
MAX_CHARACTER_LIST_CURSOR_LENGTH = 512
_MAX_DECODED_CURSOR_BYTES = 384
_BASE64URL = re.compile(r"\A[A-Za-z0-9_-]+\Z")
_UTC_MICROSECOND = re.compile(
    r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_PAYLOAD_KEYS = frozenset({"v", "project_id", "after_created_at", "after_character_id"})


class InvalidCharacterCursor(ValueError):
    """Raised without echoing an invalid Character list cursor."""

    def __init__(self) -> None:
        super().__init__("The Character list cursor is invalid.")


def _reject_json_constant(_value: str) -> Never:
    raise InvalidCharacterCursor


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidCharacterCursor
        result[key] = value
    return result


def _cursor_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def encode_character_cursor(position: CharacterListPosition) -> str:
    """Encode one position as stable compact unpadded Base64url text."""
    if type(position) is not CharacterListPosition:
        raise TypeError("position must be a CharacterListPosition")
    payload = {
        "v": CHARACTER_LIST_CURSOR_VERSION,
        "project_id": str(position.project_id),
        "after_created_at": _cursor_timestamp(position.created_at),
        "after_character_id": str(position.character_id),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    cursor = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
    if len(cursor) > MAX_CHARACTER_LIST_CURSOR_LENGTH:
        raise ValueError("encoded Character cursor exceeds the transport limit")
    return cursor


def decode_character_cursor(
    cursor: object,
    *,
    project_id: str,
) -> CharacterListPosition:
    """Decode one canonical cursor and bind it to the requested Project."""
    try:
        expected_project_id = ProjectId.parse(project_id)
    except (DomainError, TypeError):
        raise InvalidCharacterCursor from None
    if (
        type(cursor) is not str
        or not cursor
        or len(cursor) > MAX_CHARACTER_LIST_CURSOR_LENGTH
        or not cursor.isascii()
        or _BASE64URL.fullmatch(cursor) is None
    ):
        raise InvalidCharacterCursor
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        raise InvalidCharacterCursor from None
    if not decoded or len(decoded) > _MAX_DECODED_CURSOR_BYTES:
        raise InvalidCharacterCursor
    try:
        text = decoded.decode("utf-8", errors="strict")
        payload = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidCharacterCursor):
        raise InvalidCharacterCursor from None
    if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS:
        raise InvalidCharacterCursor
    version = payload.get("v")
    stored_project_id = payload.get("project_id")
    timestamp_text = payload.get("after_created_at")
    character_id = payload.get("after_character_id")
    if (
        type(version) is not int
        or version != CHARACTER_LIST_CURSOR_VERSION
        or type(stored_project_id) is not str
        or type(timestamp_text) is not str
        or type(character_id) is not str
        or _UTC_MICROSECOND.fullmatch(timestamp_text) is None
    ):
        raise InvalidCharacterCursor
    try:
        parsed_project_id = ProjectId.parse(stored_project_id)
        parsed_character_id = CharacterId.parse(character_id)
        created_at = datetime.fromisoformat(f"{timestamp_text[:-1]}+00:00")
        position = CharacterListPosition(
            project_id=parsed_project_id,
            created_at=created_at,
            character_id=parsed_character_id,
        )
    except (DomainError, TypeError, ValueError):
        raise InvalidCharacterCursor from None
    if parsed_project_id != expected_project_id:
        raise InvalidCharacterCursor
    if encode_character_cursor(position) != cursor:
        raise InvalidCharacterCursor
    return position


__all__ = [
    "CHARACTER_LIST_CURSOR_VERSION",
    "MAX_CHARACTER_LIST_CURSOR_LENGTH",
    "InvalidCharacterCursor",
    "decode_character_cursor",
    "encode_character_cursor",
]
