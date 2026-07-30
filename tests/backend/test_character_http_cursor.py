"""Canonical strict Project-bound Character cursor tests."""

import base64
import json

import pytest
from tests.backend.character_http_support import (
    BASE_TIME,
    PROJECT_ID,
    SECOND_PROJECT_ID,
)
from tests.backend.character_repository_support import character_id, project_id

from aiwebnovel.character.application.models import CharacterListPosition
from aiwebnovel.character.web.cursor import (
    InvalidCharacterCursor,
    decode_character_cursor,
    encode_character_cursor,
)


def _position() -> CharacterListPosition:
    return CharacterListPosition(project_id(1), BASE_TIME, character_id(1))


def _raw(payload: object) -> str:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def test_cursor_round_trip_is_compact_canonical_and_project_bound() -> None:
    encoded = encode_character_cursor(_position())
    assert "=" not in encoded
    assert decode_character_cursor(encoded, project_id=PROJECT_ID) == _position()
    with pytest.raises(InvalidCharacterCursor):
        decode_character_cursor(encoded, project_id=SECOND_PROJECT_ID)
    with pytest.raises(TypeError):
        encode_character_cursor(object())  # type: ignore[arg-type]
    with pytest.raises(InvalidCharacterCursor):
        decode_character_cursor(encoded, project_id="bad")


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "x" * 513,
        "%%%invalid",
        _raw({"v": 1}),
        _raw(
            {
                "v": True,
                "project_id": PROJECT_ID,
                "after_created_at": "2026-07-29T08:09:10.123456Z",
                "after_character_id": str(character_id(1)),
            }
        ),
        _raw(
            {
                "v": 1,
                "project_id": PROJECT_ID,
                "after_created_at": "2026-07-29T08:09:10Z",
                "after_character_id": str(character_id(1)),
            }
        ),
    ],
)
def test_cursor_rejects_invalid_noncanonical_payloads(cursor: str) -> None:
    with pytest.raises(InvalidCharacterCursor):
        decode_character_cursor(cursor, project_id=PROJECT_ID)


def test_cursor_rejects_duplicate_json_keys_and_padded_encoding() -> None:
    duplicate = (
        '{"after_character_id":"'
        + str(character_id(1))
        + '","after_created_at":"2026-07-29T08:09:10.123456Z",'
        f'"project_id":"{PROJECT_ID}","v":1,"v":1}}'
    )
    encoded = base64.urlsafe_b64encode(duplicate.encode()).decode().rstrip("=")
    with pytest.raises(InvalidCharacterCursor):
        decode_character_cursor(encoded, project_id=PROJECT_ID)
    with pytest.raises(InvalidCharacterCursor):
        decode_character_cursor(
            encode_character_cursor(_position()) + "=",
            project_id=PROJECT_ID,
        )


def test_cursor_rejects_noncanonical_order_invalid_ids_and_oversize_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "v": 1,
        "project_id": PROJECT_ID,
        "after_created_at": "2026-07-29T08:09:10.123456Z",
        "after_character_id": "bad",
    }
    with pytest.raises(InvalidCharacterCursor):
        decode_character_cursor(_raw(payload), project_id=PROJECT_ID)
    canonical_payload = {
        "v": 1,
        "project_id": PROJECT_ID,
        "after_created_at": "2026-07-29T08:09:10.123456Z",
        "after_character_id": str(character_id(1)),
    }
    unsorted = (
        base64.urlsafe_b64encode(json.dumps(canonical_payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    with pytest.raises(InvalidCharacterCursor):
        decode_character_cursor(unsorted, project_id=PROJECT_ID)
    monkeypatch.setattr(
        "aiwebnovel.character.web.cursor.MAX_CHARACTER_LIST_CURSOR_LENGTH",
        1,
    )
    with pytest.raises(ValueError):
        encode_character_cursor(_position())
