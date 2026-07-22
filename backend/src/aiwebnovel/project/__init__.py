"""Public framework-independent Project domain contracts."""

from aiwebnovel.domain.concurrency import ConcurrencyVersion, assert_expected_version
from aiwebnovel.domain.errors import ConcurrencyConflict
from aiwebnovel.domain.revisions import RevisionNumber
from aiwebnovel.domain.time import Clock
from aiwebnovel.project.entities import Project, ProjectAggregate, ProjectHead, ProjectRevision
from aiwebnovel.project.errors import (
    InvalidProjectDescription,
    InvalidProjectState,
    InvalidProjectTitle,
    ProjectAlreadyExists,
    ProjectDataCorruption,
    ProjectDomainError,
    ProjectNotFound,
    ProjectPersistenceConflict,
    ProjectRepositoryError,
    ProjectRevisionConflict,
)
from aiwebnovel.project.identifiers import ProjectId, ProjectRevisionId
from aiwebnovel.project.repository import ProjectRepository
from aiwebnovel.project.transitions import create_initial_project, create_next_project_revision
from aiwebnovel.project.values import ProjectDescription, ProjectTitle

__all__ = [
    "Clock",
    "ConcurrencyConflict",
    "ConcurrencyVersion",
    "InvalidProjectDescription",
    "InvalidProjectState",
    "InvalidProjectTitle",
    "Project",
    "ProjectAggregate",
    "ProjectAlreadyExists",
    "ProjectDataCorruption",
    "ProjectDescription",
    "ProjectDomainError",
    "ProjectHead",
    "ProjectId",
    "ProjectNotFound",
    "ProjectPersistenceConflict",
    "ProjectRepository",
    "ProjectRepositoryError",
    "ProjectRevision",
    "ProjectRevisionConflict",
    "ProjectRevisionId",
    "ProjectTitle",
    "RevisionNumber",
    "assert_expected_version",
    "create_initial_project",
    "create_next_project_revision",
]
