"""Canonical Project-bound immutable revision cursor tests."""

import base64
import json

import pytest

from aiwebnovel.project.application.models import ProjectRevisionHistoryPosition
from aiwebnovel.project.web.revision_cursors import (
    MAX_PROJECT_REVISION_CURSOR_LENGTH,
    InvalidProjectRevisionCursor,
    decode_project_revision_cursor,
    encode_project_revision_cursor,
)

pytestmark = pytest.mark.unit

PROJECT_ID = "prj_00000000000000000000000001"
OTHER_PROJECT_ID = "prj_00000000000000000000000002"


def encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def payload(**overrides: object) -> str:
    value: dict[str, object] = {
        "v": 1,
        "project_id": PROJECT_ID,
        "after_revision_number": 20,
    }
    value.update(overrides)
    return encoded(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def test_cursor_round_trip_is_deterministic_url_safe_and_project_bound() -> None:
    position = ProjectRevisionHistoryPosition(PROJECT_ID, 20)
    cursor = encode_project_revision_cursor(position)
    assert encode_project_revision_cursor(position) == cursor
    assert decode_project_revision_cursor(cursor, project_id=PROJECT_ID) == position
    assert all(character not in cursor for character in "=+/")
    with pytest.raises(InvalidProjectRevisionCursor):
        decode_project_revision_cursor(cursor, project_id=OTHER_PROJECT_ID)


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "a" * (MAX_PROJECT_REVISION_CURSOR_LENGTH + 1),
        "é",
        "abc+def",
        "abc/def",
        "abc=",
        "a",
        "\x00",
        encoded(b"\xff"),
        encoded(b"not-json"),
        encoded(
            b'{"after_revision_number":NaN,"project_id":"prj_00000000000000000000000001","v":1}'
        ),
        encoded(b"x" * 193),
        encoded(b"[]"),
        encoded(b"1"),
        encoded(b'{"v":1,"v":1,"project_id":"x","after_revision_number":1}'),
        encoded(b"{}"),
        payload(extra="value"),
        payload(v=0),
        payload(v=2),
        payload(v=True),
        payload(project_id=1),
        payload(project_id="bad"),
        payload(after_revision_number="1"),
        payload(after_revision_number=True),
        payload(after_revision_number=0),
        payload(after_revision_number=-1),
        payload(after_revision_number=2**63),
        encoded(
            b'{ "after_revision_number":20,"project_id":"prj_00000000000000000000000001","v":1}'
        ),
    ],
)
def test_cursor_strictly_rejects_malformed_and_noncanonical_values(cursor: object) -> None:
    with pytest.raises(InvalidProjectRevisionCursor) as captured:
        decode_project_revision_cursor(cursor, project_id=PROJECT_ID)
    assert str(captured.value) == "The Project revision cursor is invalid."


def test_cursor_rejects_noncanonical_base64_trailing_bits() -> None:
    canonical = encoded(b"{}")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    replacement = next(
        character
        for character in alphabet
        if character != canonical[-1]
        and base64.urlsafe_b64decode(canonical[:-1] + character + "=" * (-len(canonical) % 4))
        == b"{}"
    )
    with pytest.raises(InvalidProjectRevisionCursor):
        decode_project_revision_cursor(
            canonical[:-1] + replacement,
            project_id=PROJECT_ID,
        )


@pytest.mark.parametrize(
    "project_id",
    ["not-a-project-id", "prj_0000000000000000000000000z", 1, None],
)
def test_cursor_rejects_invalid_requested_project_identity(project_id: object) -> None:
    with pytest.raises(InvalidProjectRevisionCursor):
        decode_project_revision_cursor(payload(), project_id=project_id)  # type: ignore[arg-type]


def test_cursor_does_not_repr_untrusted_objects() -> None:
    class Hostile:
        def __repr__(self) -> str:
            raise AssertionError("repr must not be called")

    with pytest.raises(InvalidProjectRevisionCursor):
        decode_project_revision_cursor(Hostile(), project_id=PROJECT_ID)
    with pytest.raises(TypeError):
        encode_project_revision_cursor(object())  # type: ignore[arg-type]
