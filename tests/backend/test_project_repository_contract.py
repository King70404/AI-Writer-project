"""Public framework-independent Project repository contract tests."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from tests.backend.project_repository_support import aggregate, project_id, repository_database

from aiwebnovel.domain.concurrency import ConcurrencyVersion
from aiwebnovel.project.entities import ProjectAggregate
from aiwebnovel.project.errors import (
    InvalidProjectState,
    ProjectAlreadyExists,
    ProjectDataCorruption,
    ProjectDomainError,
    ProjectNotFound,
    ProjectPersistenceConflict,
    ProjectRepositoryError,
)
from aiwebnovel.project.persistence.repository import SqlAlchemyProjectRepository
from aiwebnovel.project.repository import ProjectRepository
from aiwebnovel.project.values import ProjectDescription

pytestmark = pytest.mark.integration

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _REPOSITORY_ROOT / "backend/src/aiwebnovel/project/repository.py"


def test_public_contract_is_pure_python_and_exposes_only_required_operations() -> None:
    source = _CONTRACT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules = {
        (node.module or "").partition(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not {"sqlalchemy", "fastapi", "pydantic"} & (imported_roots | imported_modules)
    public_methods = {
        name
        for name, member in inspect.getmembers(ProjectRepository, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {"append_revision", "create", "get"}


def test_repository_returns_detached_domain_aggregates(tmp_path: Path) -> None:
    initial = aggregate()
    with repository_database(tmp_path) as database:
        created = database.repository.create(initial)
        restored = database.repository.get(initial.project.id)

    assert type(created) is ProjectAggregate
    assert type(restored) is ProjectAggregate
    assert created == initial == restored


def test_repository_error_hierarchy_and_messages_are_safe() -> None:
    repository_errors = (
        ProjectAlreadyExists(project_id(1)),
        ProjectNotFound(project_id(1)),
        ProjectPersistenceConflict(),
        ProjectDataCorruption(),
    )
    for error in repository_errors:
        assert isinstance(error, ProjectRepositoryError)
        assert isinstance(error, ProjectDomainError)
        assert "SELECT" not in str(error)
        assert "sqlite" not in str(error).lower()
        assert "Repository canary title" not in str(error)


def test_repository_rejects_primitive_identifiers_at_contract_boundary(tmp_path: Path) -> None:
    with repository_database(tmp_path) as database, pytest.raises(InvalidProjectState):
        database.repository.get("prj_primitive")  # type: ignore[arg-type]


def test_repository_rejects_invalid_constructor_and_write_boundary_values(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError):
        SqlAlchemyProjectRepository(None)  # type: ignore[arg-type]

    with repository_database(tmp_path) as database:
        with pytest.raises(InvalidProjectState):
            database.repository.create("aggregate")  # type: ignore[arg-type]
        with pytest.raises(InvalidProjectState):
            database.repository.append_revision(
                project_id(1),
                ConcurrencyVersion(1),
                "title",  # type: ignore[arg-type]
                ProjectDescription(),
            )


def test_identifier_bearing_repository_errors_reject_primitive_ids() -> None:
    with pytest.raises(InvalidProjectState):
        ProjectAlreadyExists("project")  # type: ignore[arg-type]
    with pytest.raises(InvalidProjectState):
        ProjectNotFound("project")  # type: ignore[arg-type]
