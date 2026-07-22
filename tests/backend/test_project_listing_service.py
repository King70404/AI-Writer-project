"""Project list query service delegation tests."""

from datetime import UTC, datetime

import pytest

from aiwebnovel.project.application.models import ProjectListPage, ProjectListPosition
from aiwebnovel.project.application.queries import ListProjectsQuery
from aiwebnovel.project.application.services import ProjectListQueryService
from aiwebnovel.project.errors import ProjectDataCorruption, ProjectRepositoryError

pytestmark = pytest.mark.unit


class RecordingReader:
    def __init__(self, result: ProjectListPage | Exception) -> None:
        self.result = result
        self.calls: list[tuple[int, ProjectListPosition | None]] = []

    def list_page(
        self,
        *,
        limit: int,
        after: ProjectListPosition | None,
    ) -> ProjectListPage:
        self.calls.append((limit, after))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_service_calls_reader_once_with_the_exact_validated_query() -> None:
    page = ProjectListPage(items=(), next_position=None, has_more=False)
    reader = RecordingReader(page)
    position = ProjectListPosition(
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
        project_id="prj_00000000000000000000000001",
    )

    result = ProjectListQueryService(reader).list_projects(
        ListProjectsQuery(limit=7, after=position)
    )

    assert result is page
    assert reader.calls == [(7, position)]


@pytest.mark.parametrize("failure", [ProjectRepositoryError(), ProjectDataCorruption()])
def test_service_propagates_safe_reader_failures(failure: Exception) -> None:
    reader = RecordingReader(failure)
    with pytest.raises(type(failure)):
        ProjectListQueryService(reader).list_projects(ListProjectsQuery())
    assert reader.calls == [(20, None)]


@pytest.mark.parametrize("query", [None, object(), "query"])
def test_invalid_query_never_calls_reader(query: object) -> None:
    reader = RecordingReader(ProjectListPage(items=(), next_position=None, has_more=False))
    with pytest.raises(TypeError):
        ProjectListQueryService(reader).list_projects(query)  # type: ignore[arg-type]
    assert reader.calls == []
