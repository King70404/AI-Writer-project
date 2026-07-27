"""Shared ETag protocol and Story Bible If-Match dependency tests."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.backend.story_bible_http_support import (
    STORY_BIBLE_ID,
    isolated_app,
    issue_write_headers,
    snapshot,
)

from aiwebnovel.api.etags import (
    InvalidIfMatch,
    format_strong_etag,
    parse_strong_if_match,
)
from aiwebnovel.story_bible.application.commands import ReviseStoryBibleCommand
from aiwebnovel.story_bible.web.dependencies import get_story_bible_command_service

pytestmark = pytest.mark.unit


class ReviseService:
    def __init__(self) -> None:
        self.commands: list[ReviseStoryBibleCommand] = []

    def revise_story_bible(self, command: ReviseStoryBibleCommand):
        self.commands.append(command)
        return snapshot(version=2)


@pytest.mark.parametrize("version", [1, 2, 2**63 - 1])
def test_shared_etag_round_trip(version: int) -> None:
    value = format_strong_etag(version)
    assert value == f'"{version}"'
    assert int(parse_strong_if_match(value)) == version


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1",
        'W/"1"',
        "*",
        '"0"',
        '"-1"',
        '"01"',
        '"1.0"',
        '"1e0"',
        '"1", "2"',
        ' "1"',
        '"1" ',
        f'"{2**63}"',
    ],
)
def test_shared_etag_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(InvalidIfMatch):
        parse_strong_if_match(value)


@pytest.mark.parametrize("value", [True, 0, -1, 2**63, "1", None])
def test_shared_etag_formatter_rejects_invalid_versions(value: object) -> None:
    with pytest.raises(ValueError):
        format_strong_etag(value)


def test_story_bible_put_requires_one_if_match_value(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    service = ReviseService()
    app.dependency_overrides[get_story_bible_command_service] = lambda: service
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        missing = client.put(
            f"/api/v1/story-bibles/{STORY_BIBLE_ID}",
            headers=headers,
            json={"title": "T", "content": ""},
        )
        duplicate = client.put(
            f"/api/v1/story-bibles/{STORY_BIBLE_ID}",
            headers=[
                *headers.items(),
                ("If-Match", '"1"'),
                ("If-Match", '"2"'),
            ],
            json={"title": "T", "content": ""},
        )
        malformed = client.put(
            f"/api/v1/story-bibles/{STORY_BIBLE_ID}",
            headers={**headers, "If-Match": 'W/"1"'},
            json={"title": "T", "content": ""},
        )
    assert missing.status_code == 428
    assert missing.json()["error"]["code"] == "PRECONDITION_REQUIRED"
    assert duplicate.status_code == 400
    assert duplicate.json()["error"]["code"] == "INVALID_IF_MATCH"
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "INVALID_IF_MATCH"
    assert service.commands == []
