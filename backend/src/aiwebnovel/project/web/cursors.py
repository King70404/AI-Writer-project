"""Canonical versioned transport cursors for Project list positions."""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import UTC, datetime
from typing import Never

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.application.models import ProjectListPosition

PROJECT_LIST_CURSOR_VERSION = 1
MAX_PROJECT_LIST_CURSOR_LENGTH = 512
_MAX_DECODED_CURSOR_BYTES = 384
_BASE64URL = re.compile(r"\A[A-Za-z0-9_-]+\Z")
_PAYLOAD_KEYS = frozenset({"v", "created_at", "project_id"})


class InvalidProjectListCursor(ValueError):
    """Raised without echoing an invalid Project list cursor."""

    def __init__(self) -> None:
        super().__init__("The Project list cursor is invalid.")


def _reject_json_constant(_value: str) -> Never:
    raise InvalidProjectListCursor


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidProjectListCursor
        result[key] = value
    return result


def _cursor_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def encode_project_list_cursor(position: ProjectListPosition) -> str:
    """Encode one position as deterministic compact unpadded Base64url text."""
    if type(position) is not ProjectListPosition:
        raise TypeError("position must be a ProjectListPosition")
    payload = {
        "v": PROJECT_LIST_CURSOR_VERSION,
        "created_at": _cursor_timestamp(position.created_at),
        "project_id": position.project_id,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_project_list_cursor(cursor: object) -> ProjectListPosition:
    """Strictly decode one canonical cursor without trusting it as authorization."""
    if (
        type(cursor) is not str
        or not cursor
        or len(cursor) > MAX_PROJECT_LIST_CURSOR_LENGTH
        or not cursor.isascii()
        or _BASE64URL.fullmatch(cursor) is None
    ):
        raise InvalidProjectListCursor
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        raise InvalidProjectListCursor from None
    if not decoded or len(decoded) > _MAX_DECODED_CURSOR_BYTES:
        raise InvalidProjectListCursor
    try:
        text = decoded.decode("utf-8", errors="strict")
        payload = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidProjectListCursor):
        raise InvalidProjectListCursor from None
    if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS:
        raise InvalidProjectListCursor
    version = payload.get("v")
    timestamp_text = payload.get("created_at")
    project_id = payload.get("project_id")
    if (
        type(version) is not int
        or version != PROJECT_LIST_CURSOR_VERSION
        or type(timestamp_text) is not str
        or type(project_id) is not str
        or not timestamp_text.endswith("Z")
    ):
        raise InvalidProjectListCursor
    try:
        created_at = datetime.fromisoformat(f"{timestamp_text[:-1]}+00:00")
        position = ProjectListPosition(created_at=created_at, project_id=project_id)
    except (DomainError, TypeError, ValueError, InvalidProjectListCursor):
        raise InvalidProjectListCursor from None
    if encode_project_list_cursor(position) != cursor:
        raise InvalidProjectListCursor
    return position


__all__ = [
    "MAX_PROJECT_LIST_CURSOR_LENGTH",
    "PROJECT_LIST_CURSOR_VERSION",
    "InvalidProjectListCursor",
    "decode_project_list_cursor",
    "encode_project_list_cursor",
]
