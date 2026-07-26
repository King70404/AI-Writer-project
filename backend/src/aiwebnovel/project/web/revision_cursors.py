"""Canonical Project-bound cursors for immutable revision history."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Never

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.application.models import ProjectRevisionHistoryPosition
from aiwebnovel.project.identifiers import ProjectId

PROJECT_REVISION_CURSOR_VERSION = 1
MAX_PROJECT_REVISION_CURSOR_LENGTH = 256
_MAX_DECODED_CURSOR_BYTES = 192
_BASE64URL = re.compile(r"\A[A-Za-z0-9_-]+\Z")
_PAYLOAD_KEYS = frozenset({"v", "project_id", "after_revision_number"})


class InvalidProjectRevisionCursor(ValueError):
    """Raised without echoing an invalid revision-history cursor."""

    def __init__(self) -> None:
        super().__init__("The Project revision cursor is invalid.")


def _reject_json_constant(_value: str) -> Never:
    raise InvalidProjectRevisionCursor


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidProjectRevisionCursor
        result[key] = value
    return result


def encode_project_revision_cursor(position: ProjectRevisionHistoryPosition) -> str:
    """Encode one history position as compact unpadded Base64url text."""
    if type(position) is not ProjectRevisionHistoryPosition:
        raise TypeError("position must be a ProjectRevisionHistoryPosition")
    payload = {
        "v": PROJECT_REVISION_CURSOR_VERSION,
        "project_id": position.project_id,
        "after_revision_number": position.revision_number,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def decode_project_revision_cursor(
    cursor: object,
    *,
    project_id: str,
) -> ProjectRevisionHistoryPosition:
    """Decode one canonical cursor and bind it to the requested Project."""
    try:
        expected_project_id = str(ProjectId.parse(project_id))
    except (DomainError, TypeError, ValueError):
        raise InvalidProjectRevisionCursor from None
    if expected_project_id != project_id:
        raise InvalidProjectRevisionCursor
    if (
        type(cursor) is not str
        or not cursor
        or len(cursor) > MAX_PROJECT_REVISION_CURSOR_LENGTH
        or not cursor.isascii()
        or _BASE64URL.fullmatch(cursor) is None
    ):
        raise InvalidProjectRevisionCursor
    padding = "=" * (-len(cursor) % 4)
    try:
        decoded = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        raise InvalidProjectRevisionCursor from None
    if not decoded or len(decoded) > _MAX_DECODED_CURSOR_BYTES:
        raise InvalidProjectRevisionCursor
    try:
        payload = json.loads(
            decoded.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidProjectRevisionCursor):
        raise InvalidProjectRevisionCursor from None
    if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS:
        raise InvalidProjectRevisionCursor
    version = payload.get("v")
    payload_project_id = payload.get("project_id")
    after_revision_number = payload.get("after_revision_number")
    if (
        type(version) is not int
        or version != PROJECT_REVISION_CURSOR_VERSION
        or type(payload_project_id) is not str
        or type(after_revision_number) is not int
        or payload_project_id != expected_project_id
    ):
        raise InvalidProjectRevisionCursor
    try:
        position = ProjectRevisionHistoryPosition(
            project_id=payload_project_id,
            revision_number=after_revision_number,
        )
    except (DomainError, TypeError, ValueError):
        raise InvalidProjectRevisionCursor from None
    if encode_project_revision_cursor(position) != cursor:
        raise InvalidProjectRevisionCursor
    return position


__all__ = [
    "MAX_PROJECT_REVISION_CURSOR_LENGTH",
    "PROJECT_REVISION_CURSOR_VERSION",
    "InvalidProjectRevisionCursor",
    "decode_project_revision_cursor",
    "encode_project_revision_cursor",
]
