"""Canonical Project list cursor codec tests."""

import base64
import json
from datetime import UTC, datetime

import pytest

from aiwebnovel.project.application.models import ProjectListPosition
from aiwebnovel.project.web.cursors import (
    MAX_PROJECT_LIST_CURSOR_LENGTH,
    InvalidProjectListCursor,
    decode_project_list_cursor,
    encode_project_list_cursor,
)

pytestmark = pytest.mark.unit

PROJECT_ID = "prj_00000000000000000000000001"
LETTER_PROJECT_ID = "prj_01ARZ3NDEKTSV4RRFFQ69G5FAV"
NOW = datetime(2026, 6, 1, 2, 3, 4, 567890, tzinfo=UTC)


def _encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _payload(**overrides: object) -> str:
    payload: dict[str, object] = {
        "v": 1,
        "created_at": "2026-06-01T02:03:04.567890Z",
        "project_id": PROJECT_ID,
    }
    payload.update(overrides)
    return _encoded(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def test_cursor_round_trip_is_deterministic_url_safe_and_unpadded() -> None:
    position = ProjectListPosition(created_at=NOW, project_id=PROJECT_ID)
    first = encode_project_list_cursor(position)
    second = encode_project_list_cursor(position)

    assert first == second
    assert decode_project_list_cursor(first) == position
    assert "=" not in first
    assert "+" not in first
    assert "/" not in first
    assert first.isascii()


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "a" * (MAX_PROJECT_LIST_CURSOR_LENGTH + 1),
        "é",
        "abc+def",
        "abc/def",
        "abc=",
        "a",
        "\x00",
        _encoded(b"\xff"),
        _encoded(b"not-json"),
        _encoded(b"[]"),
        _encoded(b"1"),
        _encoded(b'{"created_at":"x","project_id":"x","v":NaN}'),
        _encoded(b'{"v":1,"v":1,"created_at":"x","project_id":"x"}'),
        _encoded(b"{}"),
        _payload(extra="value"),
        _payload(v=0),
        _payload(v=2),
        _payload(v=True),
        _payload(created_at=1),
        _payload(project_id=1),
        _payload(created_at="2026-06-01T02:03:04.567890"),
        _payload(created_at="2026-06-01T10:03:04.567890+08:00"),
        _payload(created_at="2026-06-01T02:03:04Z"),
        _payload(project_id="invalid"),
        _payload(project_id=LETTER_PROJECT_ID.lower()),
        _encoded(
            b'{ "created_at":"2026-06-01T02:03:04.567890Z",'
            b'"project_id":"prj_00000000000000000000000001","v":1}'
        ),
    ],
)
def test_cursor_strictly_rejects_malformed_or_noncanonical_values(cursor: object) -> None:
    with pytest.raises(InvalidProjectListCursor) as captured:
        decode_project_list_cursor(cursor)
    assert str(captured.value) == "The Project list cursor is invalid."


def test_cursor_rejects_noncanonical_base64_trailing_bits() -> None:
    canonical = _encoded(b"{}")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    replacement = next(
        character
        for character in alphabet
        if character != canonical[-1]
        and base64.urlsafe_b64decode(canonical[:-1] + character + "=" * (-len(canonical) % 4))
        == b"{}"
    )
    with pytest.raises(InvalidProjectListCursor):
        decode_project_list_cursor(canonical[:-1] + replacement)


def test_cursor_rejects_oversized_decoded_payload() -> None:
    cursor = _encoded(b"{" + b" " * 380 + b"}")
    assert len(cursor) <= MAX_PROJECT_LIST_CURSOR_LENGTH
    with pytest.raises(InvalidProjectListCursor):
        decode_project_list_cursor(cursor)


def test_cursor_enforces_decoded_byte_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = encode_project_list_cursor(ProjectListPosition(created_at=NOW, project_id=PROJECT_ID))
    monkeypatch.setattr("aiwebnovel.project.web.cursors._MAX_DECODED_CURSOR_BYTES", 1)
    with pytest.raises(InvalidProjectListCursor):
        decode_project_list_cursor(cursor)


def test_cursor_does_not_repr_untrusted_objects() -> None:
    class Hostile:
        def __repr__(self) -> str:
            raise AssertionError("repr must not be called")

    with pytest.raises(InvalidProjectListCursor):
        decode_project_list_cursor(Hostile())


def test_encoder_rejects_non_position_values() -> None:
    with pytest.raises(TypeError):
        encode_project_list_cursor(object())  # type: ignore[arg-type]
