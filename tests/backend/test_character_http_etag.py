"""Shared strong ETag and strict Character If-Match behavior."""

from pathlib import Path

from fastapi.testclient import TestClient
from tests.backend.character_http_support import (
    CHARACTER_ID,
    isolated_app,
    issue_write_headers,
)


def test_put_requires_one_canonical_strong_if_match(tmp_path: Path) -> None:
    app = isolated_app(tmp_path)
    payload = {"name": "A", "role": "", "profile": ""}
    with TestClient(app) as client:
        headers = issue_write_headers(client)
        missing = client.put(
            f"/api/v1/characters/{CHARACTER_ID}",
            headers=headers,
            json=payload,
        )
        malformed = client.put(
            f"/api/v1/characters/{CHARACTER_ID}",
            headers={**headers, "If-Match": 'W/"1"'},
            json=payload,
        )
        wildcard = client.put(
            f"/api/v1/characters/{CHARACTER_ID}",
            headers={**headers, "If-Match": "*"},
            json=payload,
        )
    assert missing.status_code == 428
    assert malformed.status_code == wildcard.status_code == 400
    assert missing.json()["error"]["code"] == "PRECONDITION_REQUIRED"
    assert malformed.json()["error"]["code"] == "INVALID_IF_MATCH"
