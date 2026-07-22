"""Project application query contract and one-read service behavior."""

from dataclasses import FrozenInstanceError, fields

import pytest
from tests.backend.project_repository_support import aggregate, project_id

from aiwebnovel.project.application.models import ProjectSnapshot
from aiwebnovel.project.application.queries import GetProjectQuery
from aiwebnovel.project.application.services import ProjectQueryService
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.errors import ProjectDataCorruption, ProjectRepositoryError
from aiwebnovel.project.identifiers import ProjectId

pytestmark = pytest.mark.unit


class QuerySpyRepository:
    def __init__(
        self,
        result: ProjectAggregate | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.get_calls: list[ProjectId] = []
        self.create_calls = 0
        self.append_calls = 0

    def get(self, identifier: ProjectId) -> ProjectAggregate | None:
        self.get_calls.append(identifier)
        if self.error is not None:
            raise self.error
        return self.result

    def create(self, aggregate_value: ProjectAggregate) -> ProjectAggregate:
        self.create_calls += 1
        return aggregate_value

    def append_revision(self, *args: object, **kwargs: object) -> ProjectAggregate:
        self.append_calls += 1
        raise AssertionError("query must not append a revision")


def test_get_project_query_is_raw_frozen_and_slotted() -> None:
    query = GetProjectQuery("raw-project-id")

    assert query.project_id == "raw-project-id"
    assert tuple(field.name for field in fields(query)) == ("project_id",)
    assert not hasattr(query, "__dict__")
    with pytest.raises(FrozenInstanceError):
        query.project_id = "changed"  # type: ignore[misc]


def test_query_service_parses_id_reads_once_and_maps_snapshot() -> None:
    current = aggregate(41)
    repository = QuerySpyRepository(current)
    service = ProjectQueryService(repository)
    query = GetProjectQuery(str(current.project.id))

    snapshot = service.get_project(query)

    assert isinstance(snapshot, ProjectSnapshot)
    assert snapshot.project_id == str(current.project.id)
    assert repository.get_calls == [current.project.id]
    assert repository.create_calls == 0
    assert repository.append_calls == 0
    assert query == GetProjectQuery(str(current.project.id))


def test_query_service_returns_none_for_missing_project() -> None:
    repository = QuerySpyRepository()

    result = ProjectQueryService(repository).get_project(GetProjectQuery(str(project_id(404))))

    assert result is None
    assert repository.get_calls == [project_id(404)]


def test_invalid_query_id_has_no_repository_side_effect() -> None:
    repository = QuerySpyRepository()

    with pytest.raises(Exception) as raised:
        ProjectQueryService(repository).get_project(GetProjectQuery("not-a-project-id"))

    assert raised.type.__name__ == "InvalidDomainIdentifier"
    assert repository.get_calls == []


@pytest.mark.parametrize("error", [ProjectDataCorruption(), ProjectRepositoryError()])
def test_query_service_propagates_repository_errors_unchanged(error: Exception) -> None:
    repository = QuerySpyRepository(error=error)

    with pytest.raises(type(error)) as raised:
        ProjectQueryService(repository).get_project(GetProjectQuery(str(project_id(8))))

    assert raised.value is error
    assert repository.get_calls == [project_id(8)]


class ReprTrap:
    def __repr__(self) -> str:
        raise AssertionError("query type validation must not call repr")


def test_query_service_rejects_wrong_type_without_repr_or_attribute_access() -> None:
    repository = QuerySpyRepository()

    with pytest.raises(TypeError, match="query must be a GetProjectQuery") as raised:
        ProjectQueryService(repository).get_project(ReprTrap())  # type: ignore[arg-type]

    assert "ReprTrap" not in str(raised.value)
    assert repository.get_calls == []
