"""Strict Project request/response DTO and explicit mapper tests."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from tests.backend.project_api_support import snapshot

from aiwebnovel.project.web.dto import CreateProjectRequest, ProjectResponse, ReviseProjectRequest
from aiwebnovel.project.web.mappers import project_response_from_snapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("model", [CreateProjectRequest, ReviseProjectRequest])
def test_request_dto_is_strict_frozen_and_forbids_extra(model: type[CreateProjectRequest]) -> None:
    request = model(title="  unchanged  ")
    assert request.title == "  unchanged  "
    assert request.description == ""
    with pytest.raises(ValidationError):
        model(title=123)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        model(title="Title", description=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        model(title="Title", project_id="not-accepted")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        request.title = "changed"


def test_response_mapper_copies_exact_fields_and_serializes_utc_as_rfc3339() -> None:
    source = snapshot()
    response = project_response_from_snapshot(source)

    assert set(ProjectResponse.model_fields) == {
        "project_id",
        "current_revision_id",
        "revision_number",
        "concurrency_version",
        "title",
        "description",
        "created_at",
        "updated_at",
        "revision_created_at",
        "head_updated_at",
    }
    assert response.model_dump()["title"] == source.title
    assert '"created_at":"2026-05-06T07:08:09Z"' in response.model_dump_json()
    with pytest.raises(ValidationError):
        response.title = "changed"
    with pytest.raises(TypeError):
        project_response_from_snapshot(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "timestamp",
    [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))],
)
def test_response_rejects_naive_and_non_utc_timestamps(timestamp: datetime) -> None:
    values = (
        snapshot().__dict__
        if hasattr(snapshot(), "__dict__")
        else {field: getattr(snapshot(), field) for field in ProjectResponse.model_fields}
    )
    values["created_at"] = timestamp
    with pytest.raises(ValidationError):
        ProjectResponse(**values)


def test_response_accepts_explicit_utc() -> None:
    assert snapshot().created_at.tzinfo is UTC
