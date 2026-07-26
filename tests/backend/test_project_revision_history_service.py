"""Project revision-history query service boundary tests."""

from datetime import UTC, datetime

import pytest

from aiwebnovel.domain.errors import DomainError
from aiwebnovel.project.application.models import (
    ProjectRevisionHistoryPage,
    ProjectRevisionHistoryPosition,
    ProjectRevisionHistorySnapshot,
)
from aiwebnovel.project.application.queries import (
    GetProjectRevisionQuery,
    ListProjectRevisionsQuery,
)
from aiwebnovel.project.application.services import ProjectRevisionHistoryQueryService
from aiwebnovel.project.errors import ProjectDataCorruption

pytestmark = pytest.mark.unit

PROJECT_ID = "prj_00000000000000000000000001"
OTHER_PROJECT_ID = "prj_00000000000000000000000002"
REVISION_ID = "prv_00000000000000000000000003"
NOW = datetime(2026, 7, 2, tzinfo=UTC)


class RecordingReader:
    def __init__(self, result: object) -> None:
        self.result = result
        self.list_calls: list[tuple[str, int, int | None]] = []
        self.get_calls: list[tuple[str, int]] = []

    def list_page(self, *, project_id: object, limit: int, after: object) -> object:
        self.list_calls.append((str(project_id), limit, None if after is None else int(after)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def get_revision(self, *, project_id: object, revision_number: object) -> object:
        self.get_calls.append((str(project_id), int(revision_number)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def page() -> ProjectRevisionHistoryPage:
    return ProjectRevisionHistoryPage(PROJECT_ID, 1, (), None, False)


def snapshot() -> ProjectRevisionHistorySnapshot:
    return ProjectRevisionHistorySnapshot(
        PROJECT_ID,
        REVISION_ID,
        1,
        "Title",
        "Body",
        NOW,
        True,
        1,
    )


def test_list_validates_and_delegates_exactly_once() -> None:
    reader = RecordingReader(page())
    service = ProjectRevisionHistoryQueryService(reader)  # type: ignore[arg-type]
    position = ProjectRevisionHistoryPosition(PROJECT_ID, 4)

    result = service.list_revisions(ListProjectRevisionsQuery(PROJECT_ID, limit=7, after=position))

    assert result == page()
    assert reader.list_calls == [(PROJECT_ID, 7, 4)]
    assert reader.get_calls == []


def test_get_validates_and_delegates_exactly_once() -> None:
    reader = RecordingReader(snapshot())
    service = ProjectRevisionHistoryQueryService(reader)  # type: ignore[arg-type]

    assert service.get_revision(GetProjectRevisionQuery(PROJECT_ID, 2)) == snapshot()
    assert reader.get_calls == [(PROJECT_ID, 2)]
    assert reader.list_calls == []


@pytest.mark.parametrize(
    "query",
    [
        object(),
        ListProjectRevisionsQuery("bad"),
        ListProjectRevisionsQuery(
            PROJECT_ID,
            after=ProjectRevisionHistoryPosition(OTHER_PROJECT_ID, 2),
        ),
    ],
)
def test_invalid_list_query_never_calls_reader(query: object) -> None:
    reader = RecordingReader(page())
    service = ProjectRevisionHistoryQueryService(reader)  # type: ignore[arg-type]
    with pytest.raises((DomainError, TypeError, ValueError)):
        service.list_revisions(query)  # type: ignore[arg-type]
    assert reader.list_calls == []


@pytest.mark.parametrize(
    "query",
    [object(), GetProjectRevisionQuery("bad", 1), GetProjectRevisionQuery(PROJECT_ID, True)],
)
def test_invalid_get_query_never_calls_reader(query: object) -> None:
    reader = RecordingReader(snapshot())
    service = ProjectRevisionHistoryQueryService(reader)  # type: ignore[arg-type]
    with pytest.raises((DomainError, TypeError, ValueError)):
        service.get_revision(query)  # type: ignore[arg-type]
    assert reader.get_calls == []


@pytest.mark.parametrize("method", ["list", "get"])
def test_reader_errors_propagate_safely(method: str) -> None:
    failure = ProjectDataCorruption()
    reader = RecordingReader(failure)
    service = ProjectRevisionHistoryQueryService(reader)  # type: ignore[arg-type]
    with pytest.raises(ProjectDataCorruption) as captured:
        if method == "list":
            service.list_revisions(ListProjectRevisionsQuery(PROJECT_ID))
        else:
            service.get_revision(GetProjectRevisionQuery(PROJECT_ID, 1))
    assert captured.value is failure
